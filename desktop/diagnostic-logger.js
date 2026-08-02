"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const crypto = require("crypto");

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_QUEUE = 500;
const SECRET_KEY = /api[_-]?key|authorization|cookie|password|secret|access[_-]?token|credential/i;
const SECRET_VALUE = /\b(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,})\b/gi;

function safeValue(value, key = "", depth = 0) {
  if (SECRET_KEY.test(key)) return "[REDACTED_SECRET]";
  if (depth > 5) return "[MAX_DEPTH]";
  if (value === null || value === undefined || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") return value.replace(SECRET_VALUE, "[REDACTED_SECRET]").slice(0, 2000);
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => safeValue(item, "", depth + 1));
  if (typeof value === "object") {
    return Object.fromEntries(Object.entries(value).slice(0, 100).map(([itemKey, item]) => [
      itemKey, safeValue(item, itemKey, depth + 1),
    ]));
  }
  return String(value).slice(0, 500);
}

class DesktopDiagnosticLogger {
  constructor(userDataDir) {
    this.root = path.join(userDataDir, "logs");
    this.currentDir = path.join(this.root, "desktop");
    this.archiveDir = path.join(this.root, "archive");
    this.currentPath = path.join(this.currentDir, "current.jsonl");
    this.ingestor = null;
    this.queue = [];
    this.flushing = false;
  }

  setIngestor(callback) {
    this.ingestor = callback;
  }

  log(level, event, message, fields = {}, options = {}) {
    const normalizedLevel = String(level || "INFO").toUpperCase();
    const sanitizedFields = safeValue(fields);
    const normalizedError = sanitizedFields && (sanitizedFields.error_type || sanitizedFields.error_message)
      ? {
        code: sanitizedFields.error_code || sanitizedFields.code,
        type: sanitizedFields.error_type || "Error",
        message: sanitizedFields.error_message || "",
      }
      : null;
    const payload = {
      schema: "operational-log-v1",
      event_id: `desktop_${crypto.randomBytes(12).toString("hex")}`,
      timestamp: new Date().toISOString(),
      level: normalizedLevel,
      logger: options.logger || "desktop.main",
      event: String(event || "desktop_event").slice(0, 120),
      message: safeValue(String(message || "")),
      process: "desktop",
      pid: process.pid,
      fields: sanitizedFields,
      ...(normalizedError ? { error: normalizedError } : {}),
    };
    this.write(payload);
    const consoleMethod = normalizedLevel === "ERROR" || normalizedLevel === "CRITICAL"
      ? "error" : normalizedLevel === "WARNING" ? "warn" : "log";
    console[consoleMethod](`${payload.timestamp.slice(11, 23)} ${normalizedLevel.slice(0, 3)} ${payload.logger} ${payload.message}`, payload.fields);
    if (options.forward !== false) {
      this.queue.push({
        level: payload.level,
        logger: payload.logger,
        event: payload.event,
        message: payload.message,
        process: "desktop",
        fields: {
          ...payload.fields,
          ...(normalizedError ? { error: normalizedError } : {}),
        },
      });
      if (this.queue.length > MAX_QUEUE) this.queue.splice(0, this.queue.length - MAX_QUEUE);
      void this.flush();
    }
    return payload;
  }

  write(payload) {
    try {
      fs.mkdirSync(this.currentDir, { recursive: true });
      const encoded = JSON.stringify(payload) + "\n";
      const size = fs.existsSync(this.currentPath) ? fs.statSync(this.currentPath).size : 0;
      if (size && size + Buffer.byteLength(encoded) > MAX_BYTES) this.rotate();
      fs.appendFileSync(this.currentPath, encoded, "utf8");
    } catch {
      // Logging must never terminate Electron.
    }
  }

  rotate() {
    try {
      fs.mkdirSync(this.archiveDir, { recursive: true });
      const stamp = new Date().toISOString().replaceAll(":", "-").replace(/\.\d{3}Z$/, "Z");
      const target = path.join(this.archiveDir, `desktop-${stamp}.jsonl.gz`);
      const source = fs.readFileSync(this.currentPath);
      fs.writeFileSync(target, zlib.gzipSync(source));
      fs.unlinkSync(this.currentPath);
      const archives = fs.readdirSync(this.archiveDir)
        .filter((name) => name.startsWith("desktop-") && name.endsWith(".jsonl.gz"))
        .map((name) => ({ name, path: path.join(this.archiveDir, name) }))
        .sort((left, right) => left.name.localeCompare(right.name));
      const cutoff = Date.now() - 14 * 86400 * 1000;
      for (const item of archives) {
        if (fs.statSync(item.path).mtimeMs < cutoff) fs.unlinkSync(item.path);
      }
    } catch {
      // Rotation failure degrades to console output.
    }
  }

  async flush() {
    if (!this.ingestor || this.flushing || this.queue.length === 0) return;
    this.flushing = true;
    try {
      while (this.ingestor && this.queue.length) {
        const next = this.queue[0];
        try {
          await this.ingestor(next);
          this.queue.shift();
        } catch {
          break;
        }
      }
    } finally {
      this.flushing = false;
    }
  }
}

module.exports = { DesktopDiagnosticLogger, safeValue };
