import fs from "fs";
import os from "os";
import path from "path";
import { pathToFileURL } from "url";

const pluginDir = path.resolve("C:/Users/chris/Documents/e-Sword/dragncards/vtes-dragncards-plugin");
const jsonsDir = path.join(pluginDir, "jsons");
const frontendSrc = path.resolve("C:/Users/chris/Documents/e-Sword/dragncards/DragnCards/frontend/src/features/myplugins");

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vtes-gamedef-"));
const validateSrc = fs
  .readFileSync(path.join(frontendSrc, "validate/validateGameDef.js"), "utf8")
  .replace(/import \{ sub \} from "date-fns"\s*/, "");
const schemaSrc = fs
  .readFileSync(path.join(frontendSrc, "validate/getGameDefSchema.js"), "utf8")
  .replace("./validateGameDef", "./validateGameDef.js");
fs.writeFileSync(path.join(tmpDir, "validateGameDef.js"), validateSrc);
fs.writeFileSync(path.join(tmpDir, "getGameDefSchema.js"), schemaSrc);

const { validateSchema } = await import(pathToFileURL(path.join(tmpDir, "validateGameDef.js")).href);
const { getGameDefSchema } = await import(pathToFileURL(path.join(tmpDir, "getGameDefSchema.js")).href);

function isObject(val) {
  return val && typeof val === "object" && !Array.isArray(val);
}

function deepMerge(obj1, obj2) {
  for (const p of Object.keys(obj2)) {
    if (!Object.prototype.hasOwnProperty.call(obj1, p)) {
      obj1[p] = obj2[p];
      continue;
    }
    if (obj1[p] === obj2[p]) continue;
    if (Array.isArray(obj1[p]) && Array.isArray(obj2[p])) {
      obj1[p] = [...obj1[p], ...obj2[p]];
    } else if (isObject(obj1[p]) && isObject(obj2[p])) {
      deepMerge(obj1[p], obj2[p]);
    } else {
      obj1[p] = obj2[p];
    }
  }
}

const files = fs.readdirSync(jsonsDir).filter((name) => name.endsWith(".json"));
const merged = {};
for (const file of files) {
  const parsed = JSON.parse(fs.readFileSync(path.join(jsonsDir, file), "utf8"));
  deepMerge(merged, parsed);
}

const errors = [];
validateSchema(merged, "gameDef", merged, getGameDefSchema(merged), errors);
if (errors.length) {
  console.error(`Schema errors (${errors.length}):`);
  for (const err of errors) console.error(" -", err);
  process.exit(1);
}
console.log(`Schema validation passed for ${merged.pluginName} (${files.length} JSON files).`);
