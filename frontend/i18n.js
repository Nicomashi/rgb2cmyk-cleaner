import { languages, messages } from "./locales.js";
export { languages };
export const LANGUAGE_KEY = "cmyk-clean.language";
const catalog = new Map(messages.map(([ru, en, zh]) => [ru, { ru, en, "zh-CN": zh }]));
const normalize = (text) => text.trim().replace(/\s+/g, " ");
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = messages.filter(([key]) => key.includes("{")).map(([key]) => {
  const names = [];
  let last = 0, pattern = "";
  for (const match of key.matchAll(/\{(\w+)\}/g)) {
    pattern += escapeRegExp(key.slice(last, match.index)) + "(.+?)";
    names.push(match[1]);
    last = match.index + match[0].length;
  }
  return { key, names, regex: new RegExp("^" + pattern + escapeRegExp(key.slice(last)) + "$", "s") };
});
export function createI18n(storage) {
  let language = "ru";
  try {
    const saved = storage?.getItem(LANGUAGE_KEY);
    if (Object.hasOwn(languages, saved)) language = saved;
  } catch { /* Storage can be disabled; the editor must remain usable. */ }
  function t(key, params = {}) {
    const template = catalog.get(key)?.[language] ?? key;
    return template.replace(/\{(\w+)\}/g, (token, name) => Object.hasOwn(params, name) ? String(params[name]) : token);
  }
  function translateMessage(message, depth = 0) {
    const source = String(message);
    if (["Failed to fetch", "Load failed"].includes(source)) return t("Сервер недоступен. Проверьте соединение.");
    if (catalog.has(source)) return t(source);
    if (depth < 3) for (const { key, names, regex } of patterns) {
      const match = source.match(regex);
      if (match) return t(key, Object.fromEntries(names.map((name, i) => [name,
        name === "error" ? translateMessage(match[i + 1], depth + 1) : match[i + 1]])));
    }
    return source;
  }
  return {
    get language() { return language; },
    t, translateMessage,
    setLanguage(next) {
      if (!Object.hasOwn(languages, next)) return false;
      language = next;
      try { storage?.setItem(LANGUAGE_KEY, language); } catch { /* Session-only fallback. */ }
      return true;
    },
  };
}
// Capture only known static text once. Dynamic content is rendered by workspace.js.
export function bindStaticTranslations(root, i18n) {
  const texts = [], attrs = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const key = normalize(node.data);
    if (catalog.has(key)) texts.push({ node, key,
      prefix: node.data.match(/^\s*/)[0], suffix: node.data.match(/\s*$/)[0] });
  }
  for (const node of root.querySelectorAll("*")) {
    for (const name of ["label", "aria-label", "title", "alt", "data-help", "content"]) {
      const value = node.getAttribute(name);
      if (value && catalog.has(normalize(value))) attrs.push({ node, name, key: normalize(value) });
    }
  }
  return () => {
    document.documentElement.lang = i18n.language;
    for (const node of root.querySelectorAll("sp-theme, sp-number-field, sp-slider"))
      node.lang = i18n.language;
    for (const { node, key, prefix, suffix } of texts)
      if (node.isConnected) node.data = prefix + i18n.t(key) + suffix;
    for (const { node, name, key } of attrs)
      if (node.isConnected) node.setAttribute(name, i18n.t(key));
  };
}
