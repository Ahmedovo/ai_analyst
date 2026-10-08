import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Validation } from "@/types";

interface Props {
  validation: Validation | null;
  retries: number;
  streaming?: boolean;
}

export function ValidationBadge({ validation, retries, streaming }: Props) {
  if (!validation) {
    return streaming ? (
      <Badge variant="muted">
        <ShieldQuestion className="animate-pulse" /> checking grounding…
      </Badge>
    ) : (
      <Badge variant="muted">
        <ShieldQuestion /> not validated yet
      </Badge>
    );
  }

  if (validation.note) {
    return (
      <Badge variant="muted">
        <ShieldQuestion /> {validation.note}
      </Badge>
    );
  }

  if (validation.passed === undefined) {
    // validation node never ran (e.g. agent short-circuited before it)
    return (
      <Badge variant="muted">
        <ShieldQuestion /> no verdict — the loop ended before validation
      </Badge>
    );
  }

  if (validation.passed) {
    return (
      <Badge variant="success">
        <ShieldCheck /> all {validation.checked ?? 0} number
        {(validation.checked ?? 0) === 1 ? "" : "s"} grounded
        {retries > 0 && <span className="opacity-70">· fixed after {retries} retry</span>}
      </Badge>
    );
  }

  const unsupported = validation.unsupported ?? [];
  return (
    <Badge variant="destructive">
      <ShieldAlert />
      {unsupported.length} unsupported
      {unsupported.length > 0 && `: ${unsupported.join(", ")}`}
    </Badge>
  );
}
