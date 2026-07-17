import { Action, ActionPanel, confirmAlert, Form, Icon, open, showToast, Toast } from "@raycast/api";
import { createJobPostingFile } from "../utils/job-files";
import { JOB_ROOT, sourceOptions } from "../utils/constants";
import { errorMessage } from "../utils/errors";

interface JobNewValues {
  title: string;
  company: string;
  url?: string;
  source: string;
  job_id?: string;
}

export default function JobNewCommand() {
  async function handleSubmit(values: JobNewValues) {
    try {
      const input = {
        jobRoot: JOB_ROOT,
        title: values.title,
        company: values.company,
        url: values.url ?? "",
        source: values.source,
        jobId: values.job_id?.trim() || undefined,
      };

      const created = await createJobPostingFile(input).catch(async (error: unknown) => {
        if (!errorMessage(error).includes("already exists")) {
          throw error;
        }
        const shouldOverwrite = await confirmAlert({
          title: "File Exists",
          message: "A job file with this ID already exists. Overwrite it?",
          primaryAction: { title: "Overwrite" },
        });
        if (!shouldOverwrite) {
          throw error;
        }
        return createJobPostingFile({ ...input, overwrite: true });
      });

      await showToast({
        style: Toast.Style.Success,
        title: `Created: ${created.filename}`,
        message: created.jobId,
      });

      const shouldOpen = await confirmAlert({
        title: "Open in Editor?",
        message: "Open the new job file so you can paste the full job description.",
        primaryAction: { title: "Open" },
      });
      if (shouldOpen) {
        await open(created.filePath);
      }
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not create job",
        message: errorMessage(error),
      });
    }
  }

  return (
    <Form
      navigationTitle="Job: New"
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Create Job File" icon={Icon.Plus} onSubmit={handleSubmit} />
        </ActionPanel>
      }
    >
      <Form.TextField id="title" title="Job Title" placeholder="Assistant Store Manager" />
      <Form.TextField id="company" title="Company" placeholder="Michael Kors" />
      <Form.TextField id="url" title="Job URL" placeholder="https://..." />
      <Form.Dropdown id="source" title="Source" defaultValue="linkedin">
        {sourceOptions.map((option) => (
          <Form.Dropdown.Item key={option.value} title={option.title} value={option.value} />
        ))}
      </Form.Dropdown>
      <Form.TextField id="job_id" title="Custom Job ID" placeholder="Leave blank to auto-generate" />
    </Form>
  );
}
