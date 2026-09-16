/**
 * 卡片里动态拼出来的图标。
 *
 * 页面骨架里的图标写死在 index.html，这里只放 JS 渲染时要用的那几个 ——
 * 同一段 path 原来在四个文件里各抄了一遍，改描边粗细得改四处。
 */

const svg = (body: string, extra = ''): string =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"${extra}>${body}</svg>`;

export const ICON_EDIT = svg(
  '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>' +
    '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>',
);

export const ICON_DELETE = svg(
  '<polyline points="3 6 5 6 21 6"></polyline>' +
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>',
);

export const ICON_CHECK = svg('<polyline points="20 6 9 17 4 12"></polyline>');

export const ICON_UNDO = svg('<path d="M3 3l18 18M18 6l-12 12"></path>');

export const ICON_ARROW_RIGHT = svg('<path d="M5 12h14M13 6l6 6-6 6"></path>', ' style="width: 14px; height: 14px;"');

export const ICON_INFO_CIRCLE = svg(
  '<circle cx="12" cy="12" r="10"></circle>' +
    '<line x1="12" y1="8" x2="12" y2="12"></line>' +
    '<line x1="12" y1="16" x2="12.01" y2="16"></line>',
);

export const ICON_CALENDAR = svg(
  '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>' +
    '<line x1="16" y1="2" x2="16" y2="6"></line>' +
    '<line x1="8" y1="2" x2="8" y2="6"></line>' +
    '<line x1="3" y1="10" x2="21" y2="10"></line>',
);

export const ICON_MAIL = svg(
  '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>' +
    '<polyline points="22,6 12,13 2,6"></polyline>',
);
