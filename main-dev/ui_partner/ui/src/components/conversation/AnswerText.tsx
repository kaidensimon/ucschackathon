// The answer's words. Models write Markdown; this draws it in the look: body 16/26, at most
// 608 px wide, line edges on paper, no fills. Only code is set in the mono face.
// Nothing here reaches outside the machine: a link is shown as words, a picture as its caption.
import { isValidElement, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "../shared/Button";
import { Notice, useNotYet } from "../shared/Notice";
import { NOT_YET, wght } from "../shared/words";

const BLOCK = "mb-3.5 last:mb-0";

function CodeBlock({ children }: { children?: ReactNode }) {
  const [notYet, poke] = useNotYet();
  // react-markdown hands over <pre><code>...</code></pre>: keep the words, drop the inline styling
  const code = isValidElement<{ children?: ReactNode }>(children) ? children.props.children : children;
  return (
    // the words wrap and keep clear of the button, so nothing scrolls sideways or hides under it
    <div data-part="code-block" className={`${BLOCK} relative rounded-control border border-line`}>
      <pre className="whitespace-pre-wrap break-words py-3.5 pr-20 pl-4 font-mono text-bubble text-ink">
        <code>{code}</code>
      </pre>
      <Button size="small" onClick={poke} className="absolute top-2 right-2">
        Copy
      </Button>
      {notYet ? <Notice className="px-4 pb-3">{NOT_YET}</Notice> : null}
    </div>
  );
}

// the card above holds the h2; headings inside an answer start one level down
const Heading: Components["h1"] = ({ children }) => (
  <h3 style={wght.name} className="mt-6 mb-2 text-heading first:mt-0">
    {children}
  </h3>
);
const SubHeading: Components["h3"] = ({ children }) => (
  <h4 style={wght.name} className="mt-5 mb-1.5 first:mt-0">
    {children}
  </h4>
);

const components: Components = {
  p: ({ children }) => <p className={BLOCK}>{children}</p>,
  h1: Heading,
  h2: Heading,
  h3: SubHeading,
  h4: SubHeading,
  h5: SubHeading,
  h6: SubHeading,
  ul: ({ children }) => <ul className={`${BLOCK} list-disc pl-5.5`}>{children}</ul>,
  ol: ({ children, start }) => (
    <ol start={start} className={`${BLOCK} list-decimal pl-5.5`}>
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="mt-1 pl-1 first:mt-0">{children}</li>,
  strong: ({ children }) => <strong style={wght.name}>{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className={`${BLOCK} border-line border-l-2 pl-4 text-muted`}>{children}</blockquote>
  ),
  hr: () => <hr className="my-5 border-hairline" />,
  a: ({ children, href }) => (
    <span title={href} className="underline underline-offset-2">
      {children}
    </span>
  ),
  img: ({ alt }) => (alt ? <span className="text-muted">{alt}</span> : null),
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ children }) => (
    <code className="font-mono" style={{ fontSize: "0.875em" }}>
      {children}
    </code>
  ),
  table: ({ children }) => <table className={`${BLOCK} w-full border-collapse text-left text-label`}>{children}</table>,
  th: ({ children, style }) => (
    <th scope="col" style={style} className="border-line border-b py-2 pr-4 align-bottom font-medium last:pr-0">
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td style={style} className="border-hairline border-b py-2 pr-4 align-top last:pr-0">
      {children}
    </td>
  ),
};

export function AnswerText({ text }: { text: string }) {
  return (
    <div data-part="answer-text" className="max-w-152 text-body text-ink">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </Markdown>
    </div>
  );
}
