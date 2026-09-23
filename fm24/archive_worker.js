/* Only this page's bundled Python is executable. Uploaded HTML is data only. */
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
self.onmessage = async ({data: job}) => {
  const progress = message => self.postMessage({type:'progress', message});
  try {
    progress('下載並啟動匯入引擎；第一次需要連線，檔案留在這台裝置…');
    const {loadPyodide} = await import(PYODIDE + 'pyodide.mjs');
    const py = await loadPyodide({indexURL:PYODIDE});
    await py.loadPackage(['micropip']);
    progress('準備 Excel 讀取與簡繁轉換工具…');
    await py.runPythonAsync("import micropip\nawait micropip.install(['et-xmlfile==2.0.0', 'openpyxl==3.1.5', 'opencc-python-reimplemented==0.1.7'])");
    py.FS.mkdirTree('/fm24');
    for (const [name, source] of Object.entries(job.runtime.files)) {
      if (!/^[a-z_]+\.(py|js|html|css)$/.test(name)) throw new Error('無效的引擎檔案名稱');
      py.FS.writeFile('/fm24/' + name, source);
    }
    py.FS.writeFile('/fm24/input.xlsx', new Uint8Array(job.bytes));
    py.globals.set('fm24_engine', job.runtime.engine);
    progress('核對工作表與公式、重建球員／獎項／所有賽事資料；請稍候…');
    const result = await py.runPythonAsync(`
import sys, json
sys.path.insert(0, '/fm24')
from pathlib import Path
from archive_exchange import convert, dumps
result = convert(Path('/fm24/input.xlsx'), fm24_engine)
dumps(result)
`);
    self.postMessage({type:'result', packet:JSON.parse(result)});
  } catch(error) {
    const message=String(error?.message || error).trim().split('\n').filter(Boolean).at(-1).replace(/^ValueError:\s*/, '');
    self.postMessage({type:'error', message});
  }
};
