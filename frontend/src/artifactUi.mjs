export const artifactKindLabel = (kind) => ({
  text: "文本", markdown: "Markdown", image: "图片", pdf: "PDF", data: "数据",
}[kind] || "文件");
