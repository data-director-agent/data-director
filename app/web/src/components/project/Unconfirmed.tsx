/**
 * What a repository's requirement sets leave open (`unconfirmed`), each naming the issue that will
 * settle it, shown wherever a person relies on the sets: the Repository tab and the deposit steps.
 */

export function Unconfirmed({ items, name }: { items: string[]; name: string }) {
  if (items.length === 0) return null;
  return (
    <div className="callout status-warn">
      <p>
        <strong>Not yet confirmed for {name}:</strong>
      </p>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
