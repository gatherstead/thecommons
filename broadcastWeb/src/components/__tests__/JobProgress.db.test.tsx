import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import type { JobDetail, JobTarget, TargetStatus } from "../../models/broadcastModels";
import JobProgress from "../JobProgress";

const target = (over: Partial<JobTarget> & { site_key: string; status: TargetStatus }): JobTarget => ({
  name: over.site_key.toUpperCase(),
  attempts: 0,
  dry_run: false,
  error: "",
  external_url: "",
  screenshot_url: "",
  ...over,
});

const job = (over: Partial<JobDetail> & { targets: JobTarget[] }): JobDetail => ({
  job_id: "j1",
  status: "running",
  created_at: "",
  started_at: null,
  finished_at: null,
  ...over,
});

const renderProgress = (j: JobDetail, props: Partial<React.ComponentProps<typeof JobProgress>> = {}) =>
  render(
    <JobProgress
      job={j}
      accessCode="CODE"
      onRetry={vi.fn()}
      onSubmitReal={vi.fn()}
      retrying={false}
      {...props}
    />,
  );

// The per-target badge text for a site row.
const badgeFor = (siteName: string): string =>
  screen.getByText(siteName).parentElement!.querySelector(".target-status")!.textContent!;

afterEach(cleanup);

describe("status -> label mapping", () => {
  it("renders the right badge for each backend status", () => {
    renderProgress(
      job({
        targets: [
          target({ site_key: "pend", status: "pending" }),
          target({ site_key: "prog", status: "in_progress" }),
          target({ site_key: "ready", status: "succeeded", dry_run: true }),
          target({ site_key: "sent", status: "succeeded", dry_run: false }),
          target({ site_key: "manual", status: "needs_manual" }),
          target({ site_key: "fail", status: "failed" }),
          target({ site_key: "skip", status: "skipped" }),
        ],
      }),
    );

    expect(badgeFor("PEND")).toBe("Pending");
    expect(badgeFor("PROG")).toBe("In progress");
    expect(badgeFor("READY")).toBe("Ready");
    expect(badgeFor("SENT")).toBe("Submitted");
    expect(badgeFor("MANUAL")).toBe("Needs manual");
    expect(badgeFor("FAIL")).toBe("Error");
    expect(badgeFor("SKIP")).toBe("Skipped");
  });
});

describe("optimistic submit", () => {
  it("flips a ready target to Submitted and notifies the parent", () => {
    const onSubmitReal = vi.fn();
    renderProgress(
      job({ targets: [target({ site_key: "ready", status: "succeeded", dry_run: true })] }),
      { onSubmitReal },
    );

    expect(badgeFor("READY")).toBe("Ready");

    const row = screen.getByText("READY").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Submit" }));

    expect(onSubmitReal).toHaveBeenCalledWith(["ready"]);
    expect(badgeFor("READY")).toBe("Submitted");
  });
});

describe("retry affordance", () => {
  it("shows the retry button only when finished with unfinished sites", () => {
    const { rerender } = renderProgress(
      job({ status: "running", targets: [target({ site_key: "fail", status: "failed" })] }),
    );
    // Running: no retry yet even though a site failed.
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();

    rerender(
      <JobProgress
        job={job({ status: "failed", targets: [target({ site_key: "fail", status: "failed" })] })}
        accessCode="CODE"
        onRetry={vi.fn()}
        onSubmitReal={vi.fn()}
        retrying={false}
      />,
    );
    expect(screen.getByRole("button", { name: /Retry 1 unfinished/ })).toBeInTheDocument();
  });

  it("hides retry when a finished job has no unfinished sites", () => {
    renderProgress(
      job({ status: "done", targets: [target({ site_key: "sent", status: "succeeded", dry_run: false })] }),
    );

    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });
});
