// A D1 binding backed by node:sqlite, so the worker can be run and tested on
// this laptop against the real schema. Only what worker.js uses: prepare,
// bind, all, first, run.
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

class Stmt {
  constructor(db, sql) { this.db = db; this.sql = sql; this.args = {}; }

  bind(...args) {
    // D1 takes positional values for ?1, ?2 ...; node:sqlite wants them named.
    this.args = Object.fromEntries(args.map((v, i) => [String(i + 1), v ?? null]));
    return this;
  }

  async all() { return { results: this.db.prepare(this.sql).all(this.args), success: true }; }

  async first() { return this.db.prepare(this.sql).get(this.args) ?? null; }

  async run() {
    const r = this.db.prepare(this.sql).run(this.args);
    return { success: true, meta: { last_row_id: Number(r.lastInsertRowid), changes: r.changes } };
  }
}

export function makeDb(sqlFiles = ["schema.sql"]) {
  const db = new DatabaseSync(":memory:");
  for (const f of sqlFiles) db.exec(readFileSync(join(HERE, f), "utf8"));
  return { prepare: (sql) => new Stmt(db, sql), _raw: db };
}
