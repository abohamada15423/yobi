const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('yobi', {
  onMessage: fn => ipcRenderer.on('yobi', (_e, msg) => fn(msg)),
  send: msg => ipcRenderer.send('yobi', msg),
  interactive: on => ipcRenderer.send('interactive', !!on),
  focus: on => ipcRenderer.send('focus', !!on),
  rect: r => ipcRenderer.send('rect', r),
  openSettings: () => ipcRenderer.send('open-settings'),
  // dropped files: Electron only gives their paths through webUtils
  pathFor: file => { try { return webUtils.getPathForFile(file); } catch { return ''; } },
  fileIcon: p => ipcRenderer.invoke('file-icon', p),
  dragOut: p => ipcRenderer.send('drag-out', p),
  displays: () => ipcRenderer.invoke('displays'),
});
