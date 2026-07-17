import { describe, expect, it } from "vitest";
import { JOB_ROOT_ENV_VAR, defaultJobRootCandidates, resolveJobRoot } from "../utils/constants";

describe("job root configuration", () => {
  it("uses the Raycast preference before the environment setting", () => {
    expect(
      resolveJobRoot({
        preferenceRoot: " /tmp/preferred-job-search ",
        env: { [JOB_ROOT_ENV_VAR]: "/tmp/environment-job-search" },
        candidates: ["/tmp/fallback"],
        exists: () => true,
      }),
    ).toBe("/tmp/preferred-job-search");
  });

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

  it("derives the current workspace as the default fallback", () => {
    expect(defaultJobRootCandidates("/Users/andrejspirov")[0]).toBe(
      "/Users/andrejspirov/Career/job-search",
    );
    expect(defaultJobRootCandidates("/Users/andrejspirov")).toHaveLength(1);
  });

  it("uses the first candidate when none exist and no explicit override", () => {
    expect(
      resolveJobRoot({
        env: {},
        candidates: ["/tmp/nonexistent-1", "/tmp/nonexistent-2"],
        exists: () => false,
      }),
    ).toBe("/tmp/nonexistent-1");
  });

  it("throws an error when no candidates are provided", () => {
    expect(() =>
      resolveJobRoot({
        env: {},
        candidates: [],
        exists: () => false,
      }),
    ).toThrow("Could not resolve job-search root");
  });

  it("handles paths containing spaces correctly", () => {
    expect(
      resolveJobRoot({
        preferenceRoot: " /tmp/path with spaces/job-search ",
        candidates: ["/tmp/fallback"],
        exists: () => true,
      }),
    ).toBe("/tmp/path with spaces/job-search");
  });

  it("handles custom home directory correctly", () => {
    expect(defaultJobRootCandidates("/custom/home/user")[0]).toBe(
      "/custom/home/user/Career/job-search",
    );
  });

  it("handles home directory with trailing slashes", () => {
    expect(defaultJobRootCandidates("/home/user///")[0]).toBe(
      "/home/user/Career/job-search",
    );
  });
});