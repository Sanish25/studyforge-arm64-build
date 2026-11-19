import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ChatMarkdown from "./ChatMarkdown";
import { ChatMessageView } from "./CourseChat";

it("renders markdown emphasis and a list", () => {
  render(<ChatMarkdown text={"A **DFA** has:\n\n- states\n- alphabet"} />);
  expect(screen.getByText("DFA").tagName).toBe("STRONG");
  expect(screen.getByRole("list")).toBeInTheDocument();
  expect(screen.getByText("states")).toBeInTheDocument();
});

it("renders inline LaTeX through KaTeX", () => {
  const { container } = render(<ChatMarkdown text={"Accepting state $q_f$."} />);
  expect(container.querySelector(".katex")).not.toBeNull();
  expect(container).toHaveTextContent("Accepting state");
});

it("keeps user messages as plain text and formats assistant markdown", async () => {
  const onCitation = vi.fn();
  const { rerender } = render(
    <ChatMessageView
      message={{ id: "u1", role: "user", text: "Use **stars** and $x$" }}
      onCitation={onCitation}
    />,
  );
  expect(screen.getByText("Use **stars** and $x$")).toBeInTheDocument();
  expect(document.querySelector(".chat-markdown")).toBeNull();

  rerender(
    <ChatMessageView
      message={{ id: "a1", role: "assistant", text: "A **DFA** accepts $w$." }}
      onCitation={onCitation}
    />,
  );
  // ChatMarkdown is lazy-loaded; wait for the chunk before asserting markdown/KaTeX.
  expect((await screen.findByText("DFA")).tagName).toBe("STRONG");
  expect(document.querySelector(".katex")).not.toBeNull();
});
