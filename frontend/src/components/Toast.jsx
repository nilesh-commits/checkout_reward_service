export default function Toast({ message, kind }) {
  return <div className={`toast ${kind}`}>{message}</div>;
}
