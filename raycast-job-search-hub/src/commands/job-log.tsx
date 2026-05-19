import { Action, ActionPanel, confirmAlert, Form, Icon, LaunchProps, open, showToast, Toast } from "@raycast/api";
import { format } from "date-fns";
import { useEffect, useState } from "react";
import { APPLICATIONS_CSV_PATH, outcomeOptions, sourceOptions, variantOptions } from "../utils/constants";
import { appendApplication } from "../utils/csv-parser";
import { errorMessage } from "../utils/errors";
import { extractPackMetadata } from "../utils/metadata-extractor";

interface JobLogLaunchContext {
  packDir?: string;
}

interface LogFormValues {
  date_iso?: Date;
  company: string;
  title: string;
  variant_slug: string;
  source: string;
  outcome: string;
  notes?: string;
  deadline_date?: Date;
}

interface InitialValues {
  company?: string;
  title?: string;
  variant_slug?: string;
  source?: string;
  packDir?: string;
  gapsPath?: string;
}

export default function JobLogCommand(props: LaunchProps<{ launchContext: JobLogLaunchContext }>) {
  const [initialValues, setInitialValues] = useState<InitialValues>({});
  const [isLoading, setIsLoading] = useState(Boolean(props.launchContext?.packDir));

  useEffect(() => {
    let cancelled = false;
    async function loadPack() {
      if (!props.launchContext?.packDir) {
        return;
      }
      try {
        const pack = await extractPackMetadata(props.launchContext.packDir);
        if (!cancelled) {
          setInitialValues({
            company: pack.company,
            title: pack.title,
            variant_slug: pack.variantSlug,
            source: pack.source,
            packDir: pack.dir,
            gapsPath: pack.gapsPath,
          });
        }
      } catch (error) {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not pre-fill from pack",
          message: errorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }
    loadPack();
    return () => {
      cancelled = true;
    };
  }, [props.launchContext?.packDir]);

  async function handleSubmit(values: LogFormValues) {
    try {
      if (!values.company.trim() || !values.title.trim()) {
        throw new Error("Company and title are required.");
      }
      if (!values.date_iso) {
        throw new Error("Application date is required.");
      }

      await appendApplication(APPLICATIONS_CSV_PATH, {
        date_iso: format(values.date_iso, "yyyy-MM-dd"),
        company: values.company.trim(),
        title: values.title.trim(),
        variant_slug: values.variant_slug,
        source: values.source,
        outcome: values.outcome,
        deadline_date: values.deadline_date ? format(values.deadline_date, "yyyy-MM-dd") : "",
        notes: values.notes?.trim() ?? "",
      });

      await showToast({
        style: Toast.Style.Success,
        title: `Logged: ${values.company} | ${values.title} | ${values.outcome}`,
      });

      if (values.outcome === "interview" && initialValues.gapsPath) {
        const shouldOpenGaps = await confirmAlert({
          title: "Interview Logged",
          message: "Open the keyword gaps file for this pack?",
          primaryAction: { title: "Open Gaps" },
        });
        if (shouldOpenGaps) {
          await open(initialValues.gapsPath);
        }
      }
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not log application",
        message: errorMessage(error),
      });
    }
  }

  return (
    <Form
      isLoading={isLoading}
      navigationTitle="Job: Log Application"
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Log Application" icon={Icon.Pencil} onSubmit={handleSubmit} />
        </ActionPanel>
      }
    >
      <Form.DatePicker id="date_iso" title="Application Date" defaultValue={new Date()} />
      <Form.TextField id="company" title="Company" defaultValue={initialValues.company} />
      <Form.TextField id="title" title="Role Title" defaultValue={initialValues.title} />
      <Form.Dropdown id="variant_slug" title="CV Variant" defaultValue={initialValues.variant_slug ?? "luxury-retail"}>
        {variantOptions.map((option) => (
          <Form.Dropdown.Item key={option.value} title={option.title} value={option.value} />
        ))}
      </Form.Dropdown>
      <Form.Dropdown id="source" title="Source" defaultValue={initialValues.source ?? "linkedin"}>
        {sourceOptions.map((option) => (
          <Form.Dropdown.Item key={option.value} title={option.title} value={option.value} />
        ))}
      </Form.Dropdown>
      <Form.Dropdown id="outcome" title="Outcome" defaultValue="applied">
        {outcomeOptions.map((option) => (
          <Form.Dropdown.Item key={option.value} title={option.title} value={option.value} />
        ))}
      </Form.Dropdown>
      <Form.DatePicker id="deadline_date" title="Deadline Date" />
      <Form.TextArea id="notes" title="Notes" placeholder="Applied via email" />
    </Form>
  );
}
