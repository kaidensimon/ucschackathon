import { describe, expect, it } from "vitest";
import { seatFullName, seatLabel } from "./seatName";

const label = (modelName: string, shortName = modelName.slice(0, 7)) => seatLabel({ shortName, modelName });
const full = (modelName: string, shortName = modelName.slice(0, 7)) => seatFullName({ shortName, modelName });

describe("seatLabel", () => {
  it("names the council's eight models", () => {
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
      ].map((n) => label(n)),
    ).toEqual(["GPT-OSS", "DeepSeek", "Qwen3", "Qwen3.5", "Phi-4", "Gemma 4", "Granite", "Falcon3"]);
  });

  it("does not go by the short name when the model name says more", () => {
    expect(label("DeepSeek R1 14B", "DeepSee")).toBe("DeepSeek");
    expect(label("gpt-oss 20B", "gpt")).toBe("GPT-OSS");
  });

  it("an unknown model: the family before the size, in whole words, 9 characters at most", () => {
    expect(label("qwen2.5-14b-instruct")).toBe("qwen2.5");
    expect(label("Mistral Small 24B")).toBe("Mistral");
    expect(label("gpt-oss:120b")).toBe("GPT-OSS");
    expect(label("Llama 3.1 8B")).toBe("Llama 3.1");
    expect(label("models/granite-3.3-8b.gguf")).toBe("granite");
  });

  it("a model name with no size: the seat's short name", () => {
    expect(label("Qwen example model", "Qwen")).toBe("Qwen");
    expect(label("my-finetune-v2", "Gemma")).toBe("Gemma");
    expect(label("some model", "gpt")).toBe("GPT");
  });

  it("is never longer than 9 characters for a name made of short words", () => {
    for (const n of ["DeepSeek R1 Distill 14B", "Phi-4 mini reasoning 4B", "Gemma 4 12B QAT"])
      expect(label(n).length).toBeLessThanOrEqual(9);
  });
});

describe("seatFullName", () => {
  it("gives the whole model name, its maker, and that it runs here", () => {
    expect(full("gpt-oss 20B")).toBe("GPT-OSS 20B (OpenAI, local)");
    expect(full("DeepSeek R1 14B")).toBe("DeepSeek R1 14B (DeepSeek, local)");
    expect(full("Falcon3 10B")).toBe("Falcon3 10B (Technology Innovation Institute, local)");
    expect(full("Phi-4 14B")).toBe("Phi-4 14B (Microsoft, local)");
  });

  it("a model with no known maker", () => {
    expect(full("Orca example model", "Orca")).toBe("Orca example model (local)");
  });
});
