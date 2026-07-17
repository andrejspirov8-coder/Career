import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { parseCvCataloguePayload, parseJsonPayload, runProcess, uvPythonInvocation } from "../utils/python-runner";

describe("structured process runner", () => {
  it("keeps stdout and stderr separate so warnings cannot corrupt JSON", async () => {
    const result = await runProcess(
      process.execPath,
      [
        "-e",
        "process.stdout.write(JSON.stringify({ok:true,data:{count:1}})); process.stderr.write('warning on stderr');",
      ],
      tmpdir(),
    );

    expect(result.stderr).toBe("warning on stderr");
    expect(parseJsonPayload(result.stdout)).toMatchObject({ ok: true, data: { count: 1 } });
  });

  it("includes both streams when a process exits unsuccessfully", async () => {
    await expect(
      runProcess(
        process.execPath,
        ["-e", "process.stdout.write('normal output'); process.stderr.write('error output'); process.exit(7);"],
        tmpdir(),
      ),
    ).rejects.toThrow(/stdout:\nnormal output[\s\S]*stderr:\nerror output/);
  });

  it("cancels a hung process after the configured timeout", async () => {
    await expect(
      runProcess(process.execPath, ["-e", "setInterval(() => {}, 1000);"], tmpdir(), undefined, [0], 50),
    ).rejects.toThrow(/timed out[\s\S]*cancelled/i);
  });

  it("builds every Python action through the managed uv environment", () => {
    expect(uvPythonInvocation("tools/example.py", ["--check"])).toEqual({
      command: "uv",
      args: ["run", "python", "tools/example.py", "--check"],
    });
  });

  it("validates and maps the versioned CV catalogue contract", () => {
    expect(
      parseCvCataloguePayload(
        JSON.stringify({
          schema: "career_python_helper_v1",
          ok: true,
          data: {
            schema: "cv_catalogue_v1",
            variants: [{ slug: "operations-management", name: "Operations Management" }],
          },
        }),
      ),
    ).toEqual([{ title: "Operations Management", value: "operations-management" }]);
  });
});
