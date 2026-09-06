import { formatDistance } from '../lib/format';
import type { Source } from '../types';

type SourceListProps = { sources: Source[] };

export function SourceList({ sources }: SourceListProps) {
  return (
    <ol className="sources-list">
      {sources.map((source, index) => (
        <li key={`${source.document_id}-${source.page_number}-${index}`}>
          <strong>{source.filename} · pág. {source.page_number}</strong>
          <span className="source-distance">Distancia: {formatDistance(source.distance)}</span>
          <p>{source.text}</p>
        </li>
      ))}
    </ol>
  );
}
