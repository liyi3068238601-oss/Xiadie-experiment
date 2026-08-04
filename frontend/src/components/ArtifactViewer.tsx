import { useEffect, useState } from "react";
import * as api from "../api";
import { artifactKindLabel } from "../artifactUi.mjs";

export function ArtifactViewer({ artifact }: { artifact: api.ArtifactRecord }) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    let objectUrl: string | null = null;
    let alive = true;
    api.getArtifactPreview(artifact.artifact_id)
      .then((blob) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        if (artifact.artifact_kind === "text" || artifact.artifact_kind === "markdown") {
          blob.text().then((value) => { if (alive) setText(value.slice(0, 4000)); });
        }
      })
      .catch(() => undefined);
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [artifact.artifact_id, artifact.artifact_kind]);

  return (
    <div className="artifact-preview">
      <div className="artifact-preview-meta">
        <strong>{artifact.artifact_id}</strong>
        <span>{artifactKindLabel(artifact.artifact_kind)} · v{artifact.version} · {artifact.size_bytes} B</span>
      </div>
      {artifact.artifact_kind === "image" && url && <img src={url} alt={artifact.artifact_id} />}
      {artifact.artifact_kind === "pdf" && url && (
        <iframe title={artifact.artifact_id} src={url} />
      )}
      {(artifact.artifact_kind === "text" || artifact.artifact_kind === "markdown") && (
        <pre>{text || "加载中…"}</pre>
      )}
      {artifact.artifact_kind === "data" && <p className="artifact-preview-data">二进制数据（{artifact.size_bytes} B）</p>}
    </div>
  );
}
