import { useMemo } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: true });

interface Props {
  content: string;
}

/** Sanitised markdown renderer for model answers. */
export function Markdown({ content }: Props) {
  const html = useMemo(() => {
    const raw = marked.parse(content, { async: false }) as string;
    return DOMPurify.sanitize(raw);
  }, [content]);

  return <div className="answer-md" dangerouslySetInnerHTML={{ __html: html }} />;
}
