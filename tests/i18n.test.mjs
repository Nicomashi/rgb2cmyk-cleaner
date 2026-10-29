import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createI18n, LANGUAGE_KEY } from "../frontend/i18n.js";
import { messages } from "../frontend/locales.js";

const placeholders = text => [...text.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();
test("every static interface label and tooltip has English and Chinese translations", () => {
  const keys = new Set(messages.map(row => row[0]));
  assert.equal(keys.size, messages.length, "duplicate source keys");
  for (const [source, en, zh] of messages) {
    for (const translation of [en, zh]) {
      assert.ok(translation?.trim(), source);
      assert.doesNotMatch(translation, /[А-Яа-яЁё]/, source);
      assert.deepEqual(placeholders(translation), placeholders(source), source);
    }
  }
  const html = readFileSync(new URL("../static/index.html", import.meta.url), "utf8");
  const literals = [
    ...[...html.matchAll(/>([^<>]+)</g)].map(m => m[1]),
    ...[...html.matchAll(/(?:label|aria-label|title|alt|data-help|content)="([^"]+)"/g)].map(m => m[1]),
  ];
  for (const value of literals) {
    const key = value.trim().replace(/\s+/g, " ");
    if (/[А-Яа-яЁё]/.test(key) && key !== "Русский") assert.ok(keys.has(key), key);
  }
});
test("language persists without storing image or session data", () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) };
  const first = createI18n(storage);
  assert.equal(first.language, "ru");
  assert.equal(first.setLanguage("zh-CN"), true);
  assert.equal(createI18n(storage).t("Открыть"), "打开");
  assert.deepEqual([...values], [[LANGUAGE_KEY, "zh-CN"]]);
  assert.equal(first.setLanguage("invalid"), false);
  assert.equal(first.language, "zh-CN");
  values.set(LANGUAGE_KEY, "invalid");
  assert.equal(createI18n(storage).language, "ru");
});
test("disabled browser storage does not prevent switching languages", () => {
  const i18n = createI18n({ getItem() { throw new Error(); }, setItem() { throw new Error(); } });
  i18n.setLanguage("en");
  assert.equal(i18n.t("Скачать TIFF"), "Download TIFF");
});
test("server messages, parameters and nested errors are translated without altering values", () => {
  const i18n = createI18n();
  i18n.setLanguage("en");
  assert.equal(i18n.translateMessage("Превью 2400 × 1200 px; полный экспорт 4800 × 2400 px."), "Preview 2400 × 1200 px; full export 4800 × 2400 px.");
  assert.equal(i18n.translateMessage("Не удалось получить цвет: За пределами изображения."), "Could not sample color: Outside the image bounds.");
  assert.equal(i18n.translateMessage("Не удалось открыть CMYK ICC: Нужен выходной ICC-профиль CMYK."), "Could not open CMYK ICC profile: A CMYK output ICC profile is required.");
  assert.equal(i18n.translateMessage("C до очистки"), "C before cleanup");
  assert.equal(i18n.translateMessage("Ошибка запроса (503)"), "Request failed (503)");
  assert.equal(i18n.translateMessage("Custom ICC 2026"), "Custom ICC 2026");
  i18n.setLanguage("zh-CN");
  assert.equal(i18n.t("Удалить пробник {id}", {id: 12}), "删除取样点 12");
  assert.equal(i18n.translateMessage("Страница устарела. Перезагрузите её и откройте файл заново."), "当前会话已过期。请重新加载页面并重新打开文件。");
});
