import { useRef, useState } from 'react';
import {
  Button, Dialog, DialogTrigger, Heading, Menu, MenuItem, MenuTrigger, Modal, ModalOverlay, Popover, Separator
} from 'react-aria-components';
import {
  ChevronDown, Code2, Download, FileUp, Folder, Globe, HelpCircle, Link, MoreHorizontal, PanelLeft, PanelRight, Redo2, RotateCcw, Undo2, Upload, X
} from 'lucide-react';
import { setUi, useViewer } from '../store';
import { getEngine } from '../engine/ViewerEngine';
import { toPathedFiles } from '../engine/loadModel';
import { redo, undo } from '../history';
import { BrandMark } from './BrandMark';
import { ExamplesMenu } from './ExamplesBrowser';

export function Toolbar({ mobile }: { mobile: boolean }) {
  const backend = useViewer((s) => s.backend);
  const ui = useViewer((s) => s.ui);
  const developmentVersion = location.hostname === 'mutracer-dev.meimu-studio.com'
    || (location.hostname.startsWith('mutracer-dev.') && location.hostname.endsWith('.workers.dev'));
  return (
    <header className="header">
      <div className="brand">
        <a className="brand__home" href="../" title="MuTracer home">
          <BrandMark />
          <span className="brand__name">
            <strong>{mobile ? 'MuTracer' : 'MuTracer Viewer'}</strong>
            {developmentVersion && <span className="brand__version" title="This is a development version.">
              {mobile ? 'Development' : 'Development version'}
            </span>}
          </span>
        </a>
        <span className="divider hide-m" />
        <button className="icon-btn icon-btn--bare sm hide-m" aria-label="Toggle scene panel" title="Toggle scene panel ([)"
          aria-pressed={ui.left} onClick={() => setUi({ left: !ui.left })}><PanelLeft size={15} /></button>
      </div>
      <div className="header__center">
        <OpenMenu />
        <ExamplesMenu mobile={mobile} />
      </div>
      <div className="header__right">
        <HistoryButtons />
        {!mobile && <><span className="divider" /><ResetButton /></>}
        <BackendMenu name={backend.name} adapter={backend.adapter} />
        <a className="icon-btn icon-btn--bare hide-m" href="https://github.com/pissang/mutracer" target="_blank" rel="noopener noreferrer"
          aria-label="MuTracer on GitHub (opens in a new tab)" title="MuTracer on GitHub">
          {/* GitHub Octicons mark-github-16 (MIT): https://github.com/primer/octicons/blob/main/icons/mark-github-16.svg */}
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M6.766 11.328c-2.063-.25-3.516-1.734-3.516-3.656 0-.781.281-1.625.75-2.188-.203-.515-.172-1.609.063-2.062.625-.078 1.468.25 1.968.703.594-.187 1.219-.281 1.985-.281.765 0 1.39.094 1.953.265.484-.437 1.344-.765 1.969-.687.218.422.25 1.515.046 2.047.5.593.766 1.39.766 2.203 0 1.922-1.453 3.375-3.547 3.64.531.344.89 1.094.89 1.954v1.625c0 .468.391.734.86.547C13.781 14.359 16 11.53 16 8.03 16 3.61 12.406 0 7.984 0 3.563 0 0 3.61 0 8.031a7.88 7.88 0 0 0 5.172 7.422c.422.156.828-.125.828-.547v-1.25c-.219.094-.5.156-.75.156-1.031 0-1.64-.562-2.078-1.609-.172-.422-.36-.672-.719-.719-.187-.015-.25-.093-.25-.187 0-.188.313-.328.625-.328.453 0 .844.281 1.25.86.313.452.64.655 1.031.655s.641-.14 1-.5c.266-.265.47-.5.657-.656" />
          </svg>
        </a>
        <HelpButton />
        {!mobile && <button className="btn" aria-label="显示代码" title="显示代码" onClick={() => setUi({ codeOpen: true })}>
          <Code2 size={15} /><span className="hide-xs">代码</span>
        </button>}
        {mobile && <MobileActionsMenu />}
        <button className="btn btn--primary" aria-label="导出图像" onClick={() => setUi({ exportOpen: true })}>
          <Download size={15} /><span className="hide-xs">导出</span>
        </button>
        <button className="icon-btn icon-btn--bare sm hide-m" aria-label="切换检查器" title="切换检查器 (])"
          aria-pressed={ui.right} onClick={() => setUi({ right: !ui.right })}><PanelRight size={15} /></button>
      </div>
    </header>
  );
}

function HistoryButtons() {
  const history = useViewer((s) => s.history);
  return (
    <div className="history-btns">
      <button className="icon-btn icon-btn--bare sm" aria-label="撤销" disabled={!history.undo} onClick={undo}
        title={history.undo ? `撤销 ${history.undo} (⌘Z)` : '撤销 (⌘Z)'}><Undo2 size={15} /></button>
      <button className="icon-btn icon-btn--bare sm" aria-label="重做" disabled={!history.redo} onClick={redo}
        title={history.redo ? `重做 ${history.redo} (⇧⌘Z)` : '重做 (⇧⌘Z)'}><Redo2 size={15} /></button>
    </div>
  );
}

function ResetButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="icon-btn icon-btn--bare sm" aria-label="全部重置" title="全部重置"
        onClick={() => setOpen(true)}><RotateCcw size={15} /></button>
      <ResetDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function MobileActionsMenu() {
  const [resetOpen, setResetOpen] = useState(false);
  return (
    <>
      <MenuTrigger>
        <Button className="icon-btn" aria-label="更多操作"><MoreHorizontal size={18} /></Button>
        <Popover className="popover menu" offset={8} placement="bottom end" style={{ width: 220 }}>
          <Menu className="menu-list" aria-label="更多操作" onAction={(key) => {
            if (key === 'code') setUi({ codeOpen: true });
            if (key === 'reset') setResetOpen(true);
          }}>
            <MenuItem id="code" className="menu-item"><Code2 size={15} />显示代码</MenuItem>
            <MenuItem id="reset" className="menu-item"><RotateCcw size={15} />全部重置…</MenuItem>
          </Menu>
        </Popover>
      </MenuTrigger>
      <ResetDialog open={resetOpen} onOpenChange={setResetOpen} />
    </>
  );
}

function ResetDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <ModalOverlay className="scrim" isOpen={open} onOpenChange={onOpenChange} isDismissable>
      <Modal className="dialog">
        <Dialog role="alertdialog" aria-label="全部重置">
          {({ close }) => (
            <>
              <Heading slot="title" className="dialog__title">全部重置？</Heading>
              <p className="hint">灯光、渲染设置、材质和物体显隐将恢复默认，相机会重新框住模型。此操作可撤销，但相机除外。</p>
              <div className="actions">
                <button type="button" className="btn" autoFocus onClick={close}>取消</button>
                <button type="button" className="btn btn--danger" onClick={() => { getEngine()?.resetAll(); close(); }}>全部重置</button>
              </div>
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

function OpenMenu() {
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const hdr = useRef<HTMLInputElement>(null);
  const [urlOpen, setUrlOpen] = useState(false);
  const onFiles = (list: FileList | null) => list?.length && void getEngine()?.loadFiles(toPathedFiles(list));
  return (
    <>
      <MenuTrigger>
        <Button className="btn" aria-label="打开"><Upload size={15} /><span className="hide-xs">打开</span><ChevronDown size={13} className="chev" /></Button>
        <Popover className="popover menu" offset={8} style={{ width: 250 }}>
          <Menu className="menu-list" aria-label="打开" onAction={(key) => {
            if (key === 'files') files.current?.click();
            if (key === 'folder') folder.current?.click();
            if (key === 'hdr') hdr.current?.click();
            if (key === 'url') setUrlOpen(true);
          }}>
            <MenuItem id="files" className="menu-item"><FileUp size={15} />打开文件…<kbd>⌘O</kbd></MenuItem>
            <MenuItem id="folder" className="menu-item"><Folder size={15} />打开文件夹…<kbd /></MenuItem>
            <MenuItem id="url" className="menu-item"><Link size={15} />从 URL 打开…<kbd /></MenuItem>
            <Separator className="menu-sep" />
            <MenuItem id="hdr" className="menu-item"><Globe size={15} />加载环境 (HDRI)…<kbd /></MenuItem>
          </Menu>
          <div className="menu-note">也可将文件拖到视口任意位置。</div>
        </Popover>
      </MenuTrigger>
      <input ref={files} id="open-files" type="file" hidden multiple accept=".glb,.gltf,.fbx,.stp,.step,.pbrt,.gz,.ply,.bin,.png,.jpg,.jpeg,.webp,.ktx2,.hdr,.exr,.tga,.tif,.tiff,.spd" onChange={(e) => { onFiles(e.currentTarget.files); e.currentTarget.value = ''; }} />
      <input ref={folder} type="file" hidden {...{ webkitdirectory: '' }} onChange={(e) => { onFiles(e.currentTarget.files); e.currentTarget.value = ''; }} />
      <input ref={hdr} type="file" hidden accept=".hdr" onChange={(e) => { onFiles(e.currentTarget.files); e.currentTarget.value = ''; }} />
      <UrlDialog open={urlOpen} onOpenChange={setUrlOpen} />
    </>
  );
}

function UrlDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [url, setUrl] = useState('');
  return (
    <ModalOverlay className="scrim" isOpen={open} onOpenChange={onOpenChange} isDismissable>
      <Modal className="dialog">
        <Dialog aria-label="从 URL 打开">
          {({ close }) => (
            <form onSubmit={(e) => {
              e.preventDefault();
              if (!url.trim()) return;
              void getEngine()?.loadUrl(url.trim());
              close();
            }}>
              <Heading slot="title" className="dialog__title">从 URL 打开
                <button type="button" className="icon-btn icon-btn--bare sm" aria-label="Close" onClick={close}><X size={14} /></button>
              </Heading>
              <input className="text-input" autoFocus placeholder="https://…/scene.pbrt, model.glb or environment.hdr" value={url} onChange={(e) => setUrl(e.currentTarget.value)} />
              <p className="hint">The server must allow cross-origin requests. .gltf and .pbrt files load resources relative to the scene URL.</p>
              <div className="actions">
                <button type="button" className="btn" onClick={close}>Cancel</button>
                <button type="submit" className="btn btn--primary" disabled={!url.trim()}>打开</button>
              </div>
            </form>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

function BackendMenu({ name, adapter }: { name: string | null; adapter: string }) {
  const webgl = name === 'WebGL 2';
  return (
    <MenuTrigger>
      <Button className="backend-pill hide-m" aria-label="Rendering backend">
        <i className="dot" data-tone={webgl ? 'warn' : name ? 'ok' : 'idle'} />
        <b>{name ?? '启动中'}</b>{adapter && <span className="adapter">· {adapter}</span>}
      </Button>
      <Popover className="popover menu" offset={8} placement="bottom end" style={{ width: 260 }}>
        <Menu className="menu-list" aria-label="渲染后端" onAction={(key) => {
          const url = new URL(location.href);
          if (key === 'webgl') url.searchParams.set('webgl', '');
          else url.searchParams.delete('webgl');
          location.href = url.toString();
        }}>
          <MenuItem id="webgpu" className="menu-item">WebGPU<kbd>{!webgl && name ? '当前' : ''}</kbd></MenuItem>
          <MenuItem id="webgl" className="menu-item">WebGL 2 回退<kbd>{webgl ? '当前' : ''}</kbd></MenuItem>
        </Menu>
        <div className="menu-note">切换后会重新加载页面。OIDN 与自动曝光需要 WebGPU。</div>
      </Popover>
    </MenuTrigger>
  );
}

const SHORTCUTS: [string, string][] = [
  ['拖拽 / 右键拖拽 / 滚轮', '旋转 / 平移 / 缩放'],
  ['单击', '选择物体'],
  ['F', '适配模型'],
  ['Space', '播放或暂停'],
  ['D', '开关降噪'],
  ['E', '导出图像'],
  ['1 – 4', '检查器页签'],
  ['[  ]', '场景 / 检查器面板'],
  ['H', '隐藏界面'],
  ['⌘Z  ⇧⌘Z', '撤销 / 重做材质、灯光和渲染编辑'],
  ['⌘O', '打开文件']
];

function HelpButton() {
  return (
    <DialogTrigger>
      <Button className="icon-btn icon-btn--bare hide-m" aria-label="键盘快捷键"><HelpCircle size={16} /></Button>
      <Popover className="popover" offset={8} placement="bottom end">
        <Dialog aria-label="键盘快捷键" className="shortcuts">
          <h4>快捷键</h4>
          <dl>{SHORTCUTS.map(([k, v]) => <div key={k}><dt><kbd>{k}</kbd></dt><dd>{v}</dd></div>)}</dl>
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
