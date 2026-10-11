import { describe, expect, it } from "vitest";
import { MAKERS, makerOf } from "./makers";

const of = (modelName: string, shortName = modelName) => makerOf({ shortName, modelName })?.company ?? null;

describe("makerOf", () => {
  it("knows the seven sample seats", () => {
    expect(
      ["Phi", "Llama", "Granite", "Qwen", "Gemma", "Hermes", "Mistral"].map((n) => of(`${n} example model`, n)),
    ).toEqual(["Microsoft", "Meta", "IBM", "Alibaba", "Google", "Nous Research", "Mistral AI"]);
  });

  it("reads real model file names", () => {
    expect(of("phi-4-mini-instruct-Q4_K_M.gguf")).toBe("Microsoft");
    expect(of("Meta-Llama-3.1-8B-Instruct")).toBe("Meta");
    expect(of("qwen2.5-14b-instruct")).toBe("Alibaba");
    expect(of("gemma-3-12b-it")).toBe("Google");
    expect(of("Mixtral-8x7B")).toBe("Mistral AI");
    expect(of("granite-3.3-8b")).toBe("IBM");
  });

  it("takes a family name only as a whole word", () => {
    expect(of("LlamaIndex helper")).toBeNull();
    expect(of("Sapphire-7B")).toBeNull();
    expect(of("Delphi")).toBeNull();
    expect(of("Orca example model")).toBeNull();
  });

  it("knows the makers' other families", () => {
    expect(of("CodeLlama-13b-Instruct")).toBe("Meta");
    expect(of("qwq:32b")).toBe("Alibaba");
    expect(of("codegemma:7b")).toBe("Google");
    expect(of("Ministral-8B")).toBe("Mistral AI");
    expect(of("pixtral-12b")).toBe("Mistral AI");
  });

  it("knows the council's eight models as the backend names them", () => {
    expect(
      [
        "gpt-oss 20B",
        "DeepSeek R1 14B",
        "Qwen3 14B",
        "Qwen3.5 9B",
        "Phi-4 14B",
        "Gemma 4 12B",
        "Granite 4.1 8B",
        "Falcon3 10B",
      ].map((n) => of(n, n.slice(0, 7))),
    ).toEqual([
      "OpenAI",
      "DeepSeek",
      "Alibaba",
      "Alibaba",
      "Microsoft",
      "Google",
      "IBM",
      "Technology Innovation Institute",
    ]);
    expect(of("gpt-oss:20b")).toBe("OpenAI");
    expect(of("deepseek-r1:14b")).toBe("DeepSeek");
    expect(of("falcon3:10b")).toBe("Technology Innovation Institute");
  });

  it("a distilled model belongs to the maker named first", () => {
    expect(of("DeepSeek-R1-Distill-Qwen-7B")).toBe("DeepSeek");
  });

  it("gives no logo to somebody else's model that only borrows a family name", () => {
    expect(of("Llama-3.1-Nemotron-70B")).toBeNull();
    expect(of("OpenHermes-2.5-Mistral-7B")).toBeNull();
    expect(of("Phind CodeLlama")).toBeNull();
  });

  it("reads the file's name, not the folders before it", () => {
    expect(of("llama.cpp/models/qwen2.5.gguf")).toBe("Alibaba");
  });

  it("goes by the first family named", () => {
    expect(of("Nous-Hermes-2-Mistral-7B")).toBe("Nous Research");
    expect(of("Hermes-3-Llama-3.1-8B")).toBe("Nous Research");
  });

  it("falls back to the seat's short name", () => {
    expect(of("my-finetune-v2", "Gemma")).toBe("Google");
  });

  it("every maker has a logo made of path data only", () => {
    for (const maker of Object.values(MAKERS)) {
      expect(maker.paths.length).toBeGreaterThan(0);
      for (const d of maker.paths) expect(d).toMatch(/^M[-\d.][-\d.,\sa-zA-Z]*$/);
    }
  });
});
