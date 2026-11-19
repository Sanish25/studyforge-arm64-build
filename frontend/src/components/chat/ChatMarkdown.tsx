import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/** Render assistant chat text as Markdown + LaTeX ($...$ / $$...$$). */
export default function ChatMarkdown({ text, streaming = false }: { text: string; streaming?: boolean }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {text}
      </ReactMarkdown>
      {streaming && <span className="chat-streaming-cursor" aria-hidden="true" />}
    </div>
  );
}
