// actdump: read prompts, run them through a GGUF model, write the hidden state of chosen layers.
//
// Input  (stdin, one JSON object per line):  {"id": "...", "text": "..."}
// Output (stdout, one JSON object per line): {"id": "...", "n_tokens": N, "n_embd": D,
//                                             "layers": {"<layer>": [D floats], ...}}
//
// The model file can be an Ollama blob: those are plain GGUF files.
// Layer outputs are the tensors llama.cpp names "l_out-<n>", the residual stream after block n.

#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include "nlohmann/json.hpp"

#include <clocale>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

using json = nlohmann::ordered_json;

struct capture {
    std::set<int> want;                        // empty = every layer
    bool pool_mean = false;                    // false = last token
    int n_tokens = 0;
    std::map<int, std::vector<float>> out;     // layer -> pooled vector
};

static bool cb_eval(struct ggml_tensor * t, bool ask, void * user_data) {
    auto * cap = (capture *) user_data;
    static const char * prefix = "l_out-";
    if (strncmp(t->name, prefix, strlen(prefix)) != 0) {
        return ask ? false : true;
    }
    const int layer = atoi(t->name + strlen(prefix));
    const bool wanted = cap->want.empty() || cap->want.count(layer) > 0;
    if (ask) {
        return wanted;
    }
    if (!wanted || t->type != GGML_TYPE_F32 || t->ne[1] != cap->n_tokens) {
        return true;
    }
    const int64_t n_embd = t->ne[0];
    const int64_t n_tok = t->ne[1];
    std::vector<float> all((size_t) (n_embd * n_tok));
    ggml_backend_tensor_get(t, all.data(), 0, ggml_nbytes(t));
    std::vector<float> pooled((size_t) n_embd, 0.0f);
    if (cap->pool_mean) {
        for (int64_t j = 0; j < n_tok; j++) {
            for (int64_t i = 0; i < n_embd; i++) {
                pooled[(size_t) i] += all[(size_t) (j * n_embd + i)];
            }
        }
        for (auto & v : pooled) {
            v /= (float) n_tok;
        }
    } else {
        memcpy(pooled.data(), all.data() + (size_t) ((n_tok - 1) * n_embd), sizeof(float) * (size_t) n_embd);
    }
    cap->out[layer] = std::move(pooled);
    return true;
}

static void quiet_log(enum ggml_log_level level, const char * text, void * user_data) {
    (void) user_data;
    if (level >= GGML_LOG_LEVEL_ERROR) {
        fputs(text, stderr);
    }
}

static void usage(const char * prog) {
    fprintf(stderr,
        "usage: %s -m MODEL.gguf [--layers 8,12,16 | --layers all] [--pool last|mean]\n"
        "          [-ngl N] [-c CTX] [--info]\n"
        "reads {\"id\",\"text\"} JSON lines on stdin, writes activations as JSON lines on stdout\n", prog);
}

int main(int argc, char ** argv) {
    std::setlocale(LC_NUMERIC, "C");
    std::string model_path;
    std::string layers_arg = "all";
    std::string pool = "last";
    int n_gpu_layers = 99;
    int n_ctx = 4096;
    bool info_only = false;

    for (int i = 1; i < argc; i++) {
        const std::string a = argv[i];
        const bool has_value = i + 1 < argc;
        if (a == "--info") {
            info_only = true;
        } else if (!has_value) {
            usage(argv[0]);
            return 2;
        } else if (a == "-m") {
            model_path = argv[++i];
        } else if (a == "--layers") {
            layers_arg = argv[++i];
        } else if (a == "--pool") {
            pool = argv[++i];
        } else if (a == "-ngl") {
            n_gpu_layers = atoi(argv[++i]);
        } else if (a == "-c") {
            n_ctx = atoi(argv[++i]);
        } else {
            usage(argv[0]);
            return 2;
        }
    }
    if (model_path.empty() || (pool != "last" && pool != "mean")) {
        usage(argv[0]);
        return 2;
    }

    capture cap;
    cap.pool_mean = pool == "mean";
    if (layers_arg != "all") {
        size_t start = 0;
        while (start <= layers_arg.size()) {
            size_t end = layers_arg.find(",", start);
            if (end == std::string::npos) {
                end = layers_arg.size();
            }
            if (end > start) {
                cap.want.insert(atoi(layers_arg.substr(start, end - start).c_str()));
            }
            start = end + 1;
        }
    }

    llama_log_set(quiet_log, nullptr);
    llama_backend_init();

    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = n_gpu_layers;
    llama_model * model = llama_model_load_from_file(model_path.c_str(), mparams);
    if (model == nullptr) {
        fprintf(stderr, "actdump: cannot load model %s\n", model_path.c_str());
        return 1;
    }
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const int n_layer = llama_model_n_layer(model);
    const int n_embd = llama_model_n_embd(model);

    if (info_only) {
        char arch[128] = {0};
        llama_model_meta_val_str(model, "general.architecture", arch, sizeof(arch));
        json j = {{"n_layer", n_layer}, {"n_embd", n_embd}, {"architecture", arch}};
        std::cout << j.dump() << std::endl;
        llama_model_free(model);
        llama_backend_free();
        return 0;
    }

    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = (uint32_t) n_ctx;
    cparams.n_batch = (uint32_t) n_ctx;
    cparams.cb_eval = cb_eval;
    cparams.cb_eval_user_data = &cap;
    llama_context * ctx = llama_init_from_model(model, cparams);
    if (ctx == nullptr) {
        fprintf(stderr, "actdump: cannot create context\n");
        return 1;
    }

    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }
        json in;
        try {
            in = json::parse(line);
        } catch (const std::exception & e) {
            fprintf(stderr, "actdump: bad input line: %s\n", e.what());
            continue;
        }
        const std::string text = in.value("text", "");
        json out;
        out["id"] = in.contains("id") ? in["id"] : json(nullptr);

        std::vector<llama_token> tokens(text.size() + 16);
        int n = llama_tokenize(vocab, text.c_str(), (int32_t) text.size(), tokens.data(), (int32_t) tokens.size(), true, true);
        if (n < 0) {
            tokens.resize((size_t) -n);
            n = llama_tokenize(vocab, text.c_str(), (int32_t) text.size(), tokens.data(), (int32_t) tokens.size(), true, true);
        }
        if (n <= 0 || n > n_ctx) {
            out["error"] = n <= 0 ? "empty after tokenizing" : "prompt longer than context";
            std::cout << out.dump() << std::endl;
            continue;
        }
        tokens.resize((size_t) n);

        cap.out.clear();
        cap.n_tokens = n;
        llama_memory_clear(llama_get_memory(ctx), true);
        if (llama_decode(ctx, llama_batch_get_one(tokens.data(), (int32_t) tokens.size())) != 0) {
            out["error"] = "decode failed";
            std::cout << out.dump() << std::endl;
            continue;
        }
        out["n_tokens"] = n;
        out["n_embd"] = n_embd;
        json layers = json::object();
        for (auto & kv : cap.out) {
            layers[std::to_string(kv.first)] = kv.second;
        }
        out["layers"] = layers;
        std::cout << out.dump() << std::endl;
    }

    llama_free(ctx);
    llama_model_free(model);
    llama_backend_free();
    return 0;
}
