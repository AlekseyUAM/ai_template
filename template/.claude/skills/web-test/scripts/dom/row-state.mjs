// web-test dom/row-state v1.0 — leading row-state sprite decoding
// Source: https://github.com/Nikolay-Shirokov/cc-1c-skills
/**
 * Leading list-row state icon.
 *
 * 1C draws the row state (posted / marked for deletion / completed / …) with a separate sprite,
 * coming from `e1cib/convertPicture?url=e1csys/<dir>/<file>.zip&…&gx=<N>`, where `gx` is the frame index.
 * This is NOT the same as named pic-columns (`pictureCollection/picture/<id>`) - those have a different
 * URL and a different meaning (cell value), they are parsed by picInfo() in grid.mjs.
 *
 * The dictionary key is the FULL sprite path, not the file name: `basic/folder.zip` (catalogs) and
 * `accnt/folder.zip` (chart of accounts) are different files with the same name and a DIFFERENT gx layout
 * (for basic gx=1 is an item, for accnt gx=1 is predefined). Normalizing to the file name would merge
 * them and give a wrong decoding.
 *
 * Each sprite has its own set of axes: docList → deleted+posted, folder → deleted+predefined,
 * Task → deleted+completed. An inapplicable axis is not emitted. An unknown path or an undecoded gx →
 * only `_rowPic`, without booleans: THE ABSENCE OF A BOOLEAN MEANS "I DON'T KNOW", not false.
 *
 * The layouts were captured live on ERP and confirmed by rendering the sprite frames (convertPicture&scale).
 */
export const ROW_STATE_FN = `function rowStateInfo(line) {
  // Dictionary: full path → (gx → set of axes). null = frame not decoded (only _rowPic).
  const SPRITES = {
    // Documents, document journals. The sprite is a GRID: base + 3·deletion_mark.
    // Base: 0 recorded, 1 posted, 2 "folded corner" (not decoded).
    // Exactly 6 frames (gx 6..8 are empty). gx4 (posted+marked) is unreachable in practice:
    // marking a posted document unposts it.
    'e1csys/basic/docList.zip': function (gx) {
      if (gx > 5) return null;
      const base = gx % 3, deleted = gx >= 3;
      if (base === 2) return { deleted: deleted };   // base not decoded → posted is not emitted
      return { deleted: deleted, posted: base === 1 };
    },
    // Catalogs, charts of characteristic types. We DELIBERATELY do not derive the group/item axis -
    // _kind comes from .gridListH/.gridListV, the hierarchy is based on it.
    //
    // Frames 4/5 are not an "unknown state" but a SECOND dimension: in a catalog with item
    // hierarchy (ERP «Партнеры») the parent is an item, not a folder, and the platform takes frame 4.
    // The frames are pairwise byte-for-byte equal: gx4 ≡ gx1 (pure item), gx5 ≡ gx3 (item + red
    // cross), gx8 ≡ gx7. What the second dimension means does not need to be known: the frame
    // defines both of OUR axes unambiguously (cross present → marked).
    'e1csys/basic/folder.zip': {
      0: { deleted: false, predefined: false },   // group
      1: { deleted: false, predefined: false },   // item
      2: { deleted: true,  predefined: false },   // group, marked
      3: { deleted: true,  predefined: false },   // item, marked
      4: { deleted: false, predefined: false },   // hierarchy item node (frame ≡ gx1)
      5: { deleted: true,  predefined: false },   // item node, marked (frame ≡ gx3)
      6: { deleted: false, predefined: true },    // group, predefined
      7: { deleted: false, predefined: true },    // item, predefined
      8: { deleted: false, predefined: true },    // frame ≡ gx7
    },
    // Chart of accounts - a SEPARATE sprite with the same basename but a different layout.
    'e1csys/accnt/folder.zip': {
      0: { deleted: false, predefined: false },
      1: { deleted: false, predefined: true },
      2: { deleted: true,  predefined: false },
    },
    // Tasks. Bit field: 1·Выполнена + 2·ПометкаУдаления. Verified against data on ERP.
    'e1csys/bp/Task.zip': function (gx) {
      if (gx > 3) return null;
      return { completed: (gx & 1) === 1, deleted: (gx & 2) === 2 };
    },
    // Business processes. Bit field: 4·Стартован + 2·Завершён + 1·ПометкаУдаления. Verified against data.
    'e1csys/bp/BusinessProcess.zip': function (gx) {
      if (gx > 7) return null;
      return { started: (gx & 4) === 4, finished: (gx & 2) === 2, deleted: (gx & 1) === 1 };
    },
    // Calculation type plans.
    'e1csys/calc/calcKindImg.zip': {
      0: { deleted: false, predefined: false },
      1: { deleted: true,  predefined: false },
      2: { deleted: false, predefined: true },
    },
    // Exchange plans. gx 1, 4..7 not captured → only _rowPic.
    'e1csys/backend/DataExchangeImages.zip': {
      0: { thisNode: false },
      2: { thisNode: true },
    },
  };

  function decodeUrl(s) {
    // In the DOM the path is encoded TWICE: url=e1csys%252Fbasic%252FdocList.zip
    let v = s;
    for (let i = 0; i < 3; i++) {
      let d;
      try { d = decodeURIComponent(v); } catch (e) { break; }
      if (d === v) break;
      v = d;
    }
    return v;
  }

  // A row can have several leading icons in DIFFERENT boxes: operation kind
  // (pictureCollection, an arbitrary configuration picture), tree-toggle and state.
  // That is why we iterate over all .dIB of the row instead of taking the first .gridBoxImg.
  const dibs = line.querySelectorAll('.gridBoxImg .dIB');
  for (let i = 0; i < dibs.length; i++) {
    const d = dibs[i];
    if (d.getAttribute('tree') === 'true') continue;
    const bg = d.style.backgroundImage || '';
    if (!bg.includes('convertPicture')) continue;
    const um = bg.match(/[?&]url=([^&"')]+)/);
    if (!um) continue;
    const path = decodeUrl(um[1]);
    if (!/\\.zip$/.test(path)) continue;
    const gm = bg.match(/[?&]gx=(\\d+)/);
    const gx = gm ? parseInt(gm[1], 10) : 0;

    const entry = SPRITES[path];
    const axes = typeof entry === 'function' ? entry(gx) : (entry ? entry[gx] : null);
    return { rowPic: path + ':' + gx, axes: axes || null };
  }
  return null;
}`;
