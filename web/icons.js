/* Line icons for Insights Buddy: 24 x 24, no fill, round caps and joins.
   ICONS maps a name to the inside of the <svg>; icon(name, size) returns the whole <svg> string. */
(() => {
  const ICONS = {
    smartphone: '<rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M10.5 18.5h3"/>',
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
    spark: '<path d="M11 3.5c.7 4.4 2.6 6.3 7 7-4.4.7-6.3 2.6-7 7-.7-4.4-2.6-6.3-7-7 4.4-.7 6.3-2.6 7-7z"/><path d="M18.5 15.5v5M16 18h5"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    chat: '<path d="M20 15a2 2 0 0 1-2 2H8l-4 3.5V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/>',
    phone: '<path d="M5 4h3.5l1.8 4.4-2.3 1.4a11 11 0 0 0 6.2 6.2l1.4-2.3L20 15.5V19a1.5 1.5 0 0 1-1.6 1.5A16 16 0 0 1 3.5 5.6 1.5 1.5 0 0 1 5 4z"/>',
    image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.75"/><path d="m4 18 5-5 3.5 3.5 2.5-2.5 5 5"/>',
    film: '<rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M7.5 5v14M16.5 5v14M3.5 9.5h4M3.5 14.5h4M16.5 9.5h4M16.5 14.5h4"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"/>',
    file: '<path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z"/><path d="M14 3.5v5h5M8.5 13h7M8.5 16.5h5"/>',
    sheet: '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M4 9h16M4 14.5h16M10 9v11.5"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    pin: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.5"/>',
    users: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 19.5c.6-3.3 3-5 6-5s5.4 1.7 6 5"/><path d="M15.5 5.3a3.5 3.5 0 0 1 0 6.4M17.5 14.8c1.9.6 3.1 2.2 3.5 4.7"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c.8-4 3.7-6 7.5-6s6.7 2 7.5 6"/>',
    flag: '<path d="M5 21V4.5"/><path d="M5 4.5c3-1.8 5.5-.9 7.5 0s4.5 1.8 7 .3V14c-2.5 1.5-5 .6-7 0s-4.5-1.8-7.5 0"/>',
    'flag-on': '<path d="M5 21V4.5"/><path fill="currentColor" d="M5 4.5c3-1.8 5.5-.9 7.5 0s4.5 1.8 7 .3V14c-2.5 1.5-5 .6-7 0s-4.5-1.8-7.5 0z"/>',
    face: '<circle cx="12" cy="12" r="8.5"/><path d="M9 10h.01M15 10h.01M8.8 14.5a4.5 4.5 0 0 0 6.4 0"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.7-8.7M16.5 6.5 19 9M14 9l2 2"/>',
    database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
    shield: '<path d="M12 3 5 5.8v5.7c0 4.4 3 7.9 7 9.5 4-1.6 7-5.1 7-9.5V5.8z"/><path d="m9 12 2 2 4-4"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.2-1.7l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2.9-1.7L13.3 2h-2.6l-.3 2.7a7 7 0 0 0-2.9 1.7l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 3.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2.9 1.7l.3 2.7h2.6l.3-2.7a7 7 0 0 0 2.9-1.7l2.3 1 2-3.4-2-1.5c.1-.6.2-1.1.2-1.7z"/>',
    sliders: '<path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1"/><circle cx="15" cy="6.5" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17.5" r="2"/>',
    download: '<path d="M12 3.5v11M7.5 10l4.5 4.5 4.5-4.5M4.5 17v2a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-2"/>',
    'arrow-left': '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'arrow-up': '<path d="M12 19V5M6 11l6-6 6 6"/>',
    'arrow-in': '<path d="M17 7 7 17M7 9v8h8"/>',
    'arrow-out': '<path d="M7 17 17 7M9 7h8v8"/>',
    missed: '<path d="m3.5 7.5 6 6 4-4 7 7"/><path d="M20.5 11.5v5h-5"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-up': '<path d="m6 15 6-6 6 6"/>',
    'chevron-right': '<path d="m9 6 6 6-6 6"/>',
    'chevron-left': '<path d="m15 6-6 6 6 6"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    ticks: '<path d="m2.5 12.5 4 4 8-8.5M12 15.5l1 1 8-8.5"/>',
    alert: '<path d="M10.3 4.2 2.9 17.5A2 2 0 0 0 4.6 20.5h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.9 12.1A1.5 1.5 0 0 0 8.9 20.5h6.2a1.5 1.5 0 0 0 1.5-1.4L17.5 7M10 11v5.5M14 11v5.5"/>',
    pencil: '<path d="M15.5 4.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/><path d="m13.5 6.5 4 4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    sun: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    rupee: '<path d="M7 4.5h10M7 9h10M7 4.5h3.5a4.5 4.5 0 0 1 0 9H7l7.5 6.5"/>',
    'arrows-left-right': '<path d="M4 8.5h16M16 4.5l4 4-4 4M20 15.5H4M8 11.5l-4 4 4 4"/>',
    lock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5v-3a4 4 0 0 1 8 0v3"/>',
    logout: '<path d="M9.5 20.5H6a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 6 3.5h3.5M15.5 16.5 20 12l-4.5-4.5M20 12H9.5"/>',
    play: '<path d="M7.5 5v14l11-7z"/>',
    copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5v-3a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/>',
    eye: '<path d="M2.5 12C4.5 8 8 5.5 12 5.5s7.5 2.5 9.5 6.5c-2 4-5.5 6.5-9.5 6.5S4.5 16 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    sidebar: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4.5h-4.5"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    camera: '<path d="M4.5 7.5h3L9 5h6l1.5 2.5h3A1.5 1.5 0 0 1 21 9v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18V9a1.5 1.5 0 0 1 1.5-1.5z"/><circle cx="12" cy="13" r="3.5"/>',
    mail: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    wifi: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01"/>',
    sim: '<path d="M7 3.5h7l4 4v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2z"/><rect x="8.5" y="11" width="7" height="6.5" rx="1"/>',
    tag: '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-6.6 6.6a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8" cy="8" r="1.5"/>',
    notes: '<rect x="5" y="3.5" width="14" height="17" rx="2"/><path d="M8.5 8h7M8.5 12h7M8.5 16h4"/>',
    list: '<path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01"/>',
    case: '<rect x="3.5" y="7" width="17" height="12.5" rx="2"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3.5 12.5h17"/>',
    more: '<circle cx="5.5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18.5" cy="12" r="1"/>',
    'text-size': '<path d="M4 7V5h9v2M8.5 5v14M6.5 19h4M14 12v-1.5h6V12M17 10.5V19M15.5 19h3"/>',
    'app-whatsapp': '<path d="M4 20.5l1.3-4A8.5 8.5 0 1 1 8.2 19z"/><path d="M9 9.2c.2 2.9 2.9 5.6 5.8 5.8l1.2-1.6-2-1.1-.9.8c-.9-.4-1.8-1.3-2.2-2.2l.8-.9-1.1-2z"/>',
    'app-sms': '<path d="M20 15.5a2 2 0 0 1-2 2H8.5L4 21V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/><path d="M8 8.5h8M8 12.5h5"/>',
    'app-telegram': '<path d="M21 4 3 11l6.5 2.5L12 20l3-4.5 4.5 3.5z"/><path d="m9.5 13.5 11.5-9.5"/>',
    'app-signal': '<path d="M5 19.5l.9-3.4A8 8 0 1 1 8.8 18.7z"/><path d="M9 11.5h6"/>',
    'app-imessage': '<path d="M12 4c4.7 0 8.5 3.1 8.5 7s-3.8 7-8.5 7c-.9 0-1.8-.1-2.6-.3L5 19.5l1.2-3.3C4.6 14.9 3.5 13.1 3.5 11c0-3.9 3.8-7 8.5-7z"/>'
  };

  function icon(name, size = 18, extra = '') {
    const body = ICONS[name] || ICONS.info;
    return `<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"${extra ? ' ' + extra : ''}>${body}</svg>`;
  }

  const IB = (window.IB = window.IB || {});
  IB.ICONS = ICONS;
  IB.icon = icon;
  window.icon = icon;
})();
