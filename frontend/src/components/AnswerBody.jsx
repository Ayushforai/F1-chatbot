import { parseAnswer, tokenizeInline } from "../formatAnswer.js";

function InlineText({ text }) {
  return tokenizeInline(text).map((token, i) =>
    token.bold ? <strong key={i}>{token.text}</strong> : <span key={i}>{token.text}</span>
  );
}

export default function AnswerBody({ text }) {
  const nodes = parseAnswer(text);
  if (!nodes.length) return null;

  return (
    <div className="answer-body">
      {nodes.map((node, i) => {
        if (node.type === "heading") {
          const Tag = node.level <= 2 ? "h3" : "h4";
          return (
            <Tag key={i} className={`answer-heading level-${node.level}`}>
              <InlineText text={node.text} />
            </Tag>
          );
        }
        if (node.type === "list") {
          const List = node.ordered ? "ol" : "ul";
          return (
            <List key={i} className="answer-list">
              {node.items.map((item, j) => (
                <li key={j} className={`indent-${item.indent || 0}`}>
                  <InlineText text={item.text} />
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i} className="answer-p">
            <InlineText text={node.text} />
          </p>
        );
      })}
    </div>
  );
}
