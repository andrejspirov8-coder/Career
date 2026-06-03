import { describe, expect, it } from "vitest";
import { JOB_ROOT_ENV_VAR, defaultJobRootCandidates, resolveJobRoot } from "../utils/constants";

describe("job root configuration", () => {
  it("uses the explicit environment setting when present", () => {
    expect(
      resolveJobRoot({
        env: { [JOB_ROOT_ENV_VAR]: " /tmp/custom-job-search " },
        candidates: ["/tmp/fallback"],
        exists: () => true,
      }),
    ).toBe("/tmp/custom-job-search");
  });

  it("chooses the first existing fallback candidate", () => {
    expect(
      resolveJobRoot({
        env: {},
        candidates: ["/tmp/missing-job-search", "/tmp/actual-job-search"],
        exists: (path) => path === "/tmp/actual-job-search",
      }),
    ).toBe("/tmp/actual-job-search");
  });

  it("checks the current Career-main checkout before legacy fallback folders", () => {
    expect(defaultJobRootCandidates("/Users/andrejspirov")[0]).toBe(
      "/Users/andrejspirov/Career/Career-main/job-search",
    );
  });
});
