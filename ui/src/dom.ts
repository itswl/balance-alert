/**
 * DOM 取用的收口。
 *
 * 原生 JS 版到处写 `document.getElementById('x').value`，元素被改名时崩在一句
 * "Cannot read properties of null" 上，看不出是哪个 id。这里把「页面骨架保证存在」
 * 和「可能不存在」两类分开：前者用 require* 抛带 id 的错，后者返回 null 由调用方判断。
 */

/** 可能不存在的元素（受功能开关控制的按钮之类） */
export function byId<T extends HTMLElement = HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

/** index.html 骨架里保证存在的元素；缺了说明模板被改坏，早失败好过静默错渲染 */
export function requireById<T extends HTMLElement = HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`页面缺少元素 #${id}`);
  return node as T;
}

export function inputById(id: string): HTMLInputElement {
  return requireById<HTMLInputElement>(id);
}

export function selectById(id: string): HTMLSelectElement {
  return requireById<HTMLSelectElement>(id);
}

/** 读输入框的值并去掉首尾空白 */
export function inputValue(id: string): string {
  return inputById(id).value.trim();
}

export function setInputValue(id: string, value: string | number | null | undefined): void {
  inputById(id).value = value === null || value === undefined ? '' : String(value);
}

export function isChecked(id: string): boolean {
  return inputById(id).checked;
}

export function setChecked(id: string, checked: boolean): void {
  inputById(id).checked = checked;
}

export function setText(id: string, text: string): void {
  const node = byId(id);
  if (node) node.textContent = text;
}

/** 按功能开关显示 / 隐藏一个按钮；display 值跟原来保持一致，否则布局会塌 */
export function toggleDisplay(id: string, visible: boolean, shown = 'inline-flex'): void {
  const node = byId(id);
  if (node) node.style.display = visible ? shown : 'none';
}

export function onClick(id: string, handler: (event: MouseEvent) => void): void {
  byId(id)?.addEventListener('click', handler as EventListener);
}

/** 同一批带类名的按钮（弹窗里「关闭」出现在标题栏和底栏两处） */
export function onClickAll(selector: string, handler: (event: MouseEvent) => void): void {
  document.querySelectorAll<HTMLElement>(selector).forEach((node) => {
    node.addEventListener('click', handler as EventListener);
  });
}

/** 填下拉框；selected 命中的项会被选中 */
export function fillSelect(
  select: HTMLSelectElement,
  options: Array<{ value: string; label: string }>,
  selected = '',
): void {
  select.innerHTML = '';
  for (const { value, label } of options) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    option.selected = value === selected;
    select.appendChild(option);
  }
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, wait: number): (...args: A) => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: A): void => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
