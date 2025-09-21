import { app } from "/scripts/app.js";
/*
  ComfyUI Frontend Extension: Turn role_name combo into a collapsible tree menu.
  Target node: "🦉Load Preset Prompt" (class: Load_Preset_Prompt_Node)
  Place this file under: custom_nodes/Comfyui_Free_API/web/role_tree_menu.js
*/

(function () {
  const EXT_NAME = "FreeAPI.PromptEnhance.TreeMenu";

  function log(...args) {
    try { console.log("[TreeMenu]", ...args); } catch (_) {}
  }
  function warn(...args) {
    try { console.warn("[TreeMenu]", ...args); } catch (_) {}
  }

  function isTargetNode(node) {
    return (
      node?.title === "🦉Load Preset Prompt" ||
      node?.comfyClass === "Load_Preset_Prompt_Node"
    );
  }

  function getRoleWidget(node) {
    if (!node?.widgets) return null;
    return node.widgets.find((w) => w && (w.name === "role_name" || w.label === "role_name"));
  }

  function buildTree(paths) {
    const root = { name: "", children: new Map(), files: [] };
    for (const p of paths) {
      if (typeof p !== "string" || !p.trim()) continue;
      const parts = p.split("/").filter(Boolean);
      if (parts.length === 0) continue;
      if (parts.length === 1) {
        root.files.push({ label: parts[0], value: p });
      } else {
        let cur = root;
        for (let i = 0; i < parts.length - 1; i++) {
          const seg = parts[i];
          if (!cur.children.has(seg)) {
            cur.children.set(seg, { name: seg, children: new Map(), files: [] });
          }
          cur = cur.children.get(seg);
        }
        const leaf = parts[parts.length - 1];
        cur.files.push({ label: leaf, value: p });
      }
    }
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    function sortNode(node) {
      node.files.sort((a, b) => collator.compare(a.label, b.label));
      const sortedChildren = [...node.children.values()].sort((a, b) =>
        collator.compare(a.name, b.name)
      );
      node.children = new Map(sortedChildren.map((n) => [n.name, sortNode(n)]));
      return node;
    }
    return sortNode(root);
  }

  function treeToMenuItems(node) {
    const items = [];
    for (const child of node.children.values()) {
      items.push({
        content: child.name,
        has_submenu: true,
        submenu: { options: treeToMenuItems(child) },
      });
    }
    for (const f of node.files) {
      items.push({ content: f.label, value: f.value });
    }
    return items;
  }

  // Always return a flat string list for internal combo validation
  function flatValuesProvider(originalProvider) {
    return function () {
      try {
        const values = Array.isArray(originalProvider)
          ? originalProvider
          : typeof originalProvider === "function"
          ? originalProvider()
          : [];
        return (values || []).filter((v) => typeof v === "string");
      } catch (err) {
        warn("flatValuesProvider error, fallback:", err);
        return typeof originalProvider === "function" ? originalProvider() : (originalProvider || []);
      }
    };
  }

  function wrapValuesProvider(originalProvider) {
    return function () {
      try {
        const values = Array.isArray(originalProvider)
          ? originalProvider
          : (typeof originalProvider === "function" ? originalProvider() : []);
        const flat = (values || []).filter((v) => typeof v === "string");
        const tree = buildTree(flat);
        const menuItems = treeToMenuItems(tree);
        return menuItems.length ? menuItems : values;
      } catch (err) {
        warn("Fallback to flat list due to error:", err);
        return typeof originalProvider === "function" ? originalProvider() : originalProvider;
      }
    };
  }

  function patchComboWidget(widget) {
    if (!widget || widget.type !== "combo" || !widget.options) return false;
    // 保持原生字符串列表，不返回对象树；树形展示改为 DOM 重排（更稳定）
    const origValues = widget.options.values;
    widget.options.values = origValues;

    // 保持原生赋值与回调，不拦截 value，避免和内置选择流程冲突

    // 不覆写 callback，沿用原生行为

    log("Widget patched:", widget.name || widget.label);
    return true;
  }

  // 命中检测：判断点击是否在指定节点的某个 widget 区域内
  function hitRoleWidget(node, widget, canvas, evt) {
    try {
      if (!node || !widget || !canvas) return false;
      // 转换事件到画布坐标
      let x = evt.canvasX, y = evt.canvasY;
      if ((x === undefined || y === undefined) && typeof canvas.convertEventToCanvasOffset === "function") {
        const off = canvas.convertEventToCanvasOffset(evt);
        x = off[0]; y = off[1];
      }
      if (x === undefined || y === undefined) return false;

      const zoom = canvas.zoom || 1;
      const npos = node.pos; // [x,y] in canvas space
      const width = node.size ? node.size[0] : 200;
      const widget_y = (node.widgets_start_y || 0) + (widget.y || 0);
      const w_h = widget.height || LiteGraph.NODE_WIDGET_HEIGHT || 20;

      const left = npos[0] + 10;
      const right = npos[0] + width - 10;
      const top = npos[1] + widget_y;
      const bottom = top + w_h;

      return x >= left && x <= right && y >= top && y <= bottom;
    } catch (_) {
      return false;
    }
  }

  app.registerExtension({
    name: EXT_NAME,
    async setup() {
      log("extension loaded");

      // 参考 pysssss betterCombos：样式与“有过滤词时回退为平铺”的规则
      const style = document.createElement("style");
      style.textContent = `
        .freeapi-tree-folder { opacity: 0.8 }
        .freeapi-tree-folder-arrow { display: inline-block; width: 15px; }
        .freeapi-tree-folder:hover { background-color: rgba(255,255,255,0.1); }
        .freeapi-tree-prefix { display: none }

        /* 当搜索框有内容时，恢复为普通平铺列表，便于过滤 */
        .litecontextmenu:has(input:not(:placeholder-shown)) .freeapi-tree-contents { display: block !important; }
        .litecontextmenu:has(input:not(:placeholder-shown)) .freeapi-tree-folder { display: none; }
        .litecontextmenu:has(input:not(:placeholder-shown)) .freeapi-tree-prefix { display: inline; }
        .litecontextmenu:has(input:not(:placeholder-shown)) .litemenu-entry { padding-left: 2px !important; }
      `;
      document.body.appendChild(style);

      // 监听菜单创建，命中我们的 role_name 时进行 DOM 重排为折叠目录
      const { $el } = await import("/scripts/ui.js");
      const mutationObserver = new MutationObserver((mutations) => {
        const node = app.canvas?.current_node;
        if (!node || !isTargetNode(node)) return;

        for (const m of mutations) {
          for (const added of m.addedNodes) {
            if (!added.classList?.contains("litecontextmenu")) continue;

            const overWidget = app.canvas.getWidgetAtCursor?.();
            if (overWidget?.name !== "role_name") return;

            // 仅处理包含 Filter input 的主下拉，而不是右键菜单
            if (!added.querySelector?.(".comfy-context-menu-filter")) return;

            // 等待原始项渲染完成
            requestAnimationFrame(() => {
              const items = added.querySelectorAll(".litemenu-entry");
              if (!items?.length) return;

              const folderMap = new Map();
              const rootItems = [];
              const itemsSymbol = Symbol("items");

              const splitBy = /\//;

              // 一次性构建目录结构，并把可过滤前缀写回隐藏 span
              for (const item of items) {
                const full = item.getAttribute("data-value")?.trim() || "";
                if (!full) continue;
                const path = full.split(splitBy).filter(Boolean);
                // 可视名称仅显示叶子
                item.textContent = path[path.length - 1] || full;
                if (path.length > 1) {
                  const prefix = document.createElement("span");
                  prefix.className = "freeapi-tree-prefix";
                  prefix.textContent = path.slice(0, -1).join("/") + "/";
                  item.prepend(prefix);
                }

                if (path.length === 1) {
                  rootItems.push(item);
                  continue;
                }

                // 先移除，后续再插入到对应目录块
                item.remove();

                let cur = folderMap;
                for (let i = 0; i < path.length - 1; i++) {
                  const seg = path[i];
                  if (!cur.has(seg)) cur.set(seg, new Map());
                  cur = cur.get(seg);
                }
                if (!cur.has(itemsSymbol)) cur.set(itemsSymbol, []);
                cur.get(itemsSymbol).push(item);
              }

              const createFolder = (name) => {
                const div = document.createElement("div");
                div.className = "litemenu-entry freeapi-tree-folder";
                div.innerHTML = `<span class="freeapi-tree-folder-arrow">▶</span> ${name}`;
                div.style.paddingLeft = "5px";
                return div;
              };

              const insertTree = (parent, map, level = 0) => {
                // 稳定排序：目录名按自然顺序
                const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
                const entries = [...map.entries()].sort((a, b) => {
                  if (a[0] === itemsSymbol) return 1;
                  if (b[0] === itemsSymbol) return -1;
                  return collator.compare(a[0], b[0]);
                });

                for (const [folderName, content] of entries) {
                  if (folderName === itemsSymbol) continue;

                  const folderEl = createFolder(folderName);
                  folderEl.style.paddingLeft = `${level * 10 + 5}px`;
                  parent.appendChild(folderEl);

                  const container = document.createElement("div");
                  container.className = "freeapi-tree-contents";
                  container.style.display = "none";

                  const files = (content.get(itemsSymbol) || []).slice().sort((a, b) => {
                    return a.textContent.localeCompare(b.textContent, undefined, { numeric: true, sensitivity: "base" });
                  });
                  for (const it of files) {
                    it.style.paddingLeft = `${(level + 1) * 10 + 14}px`;
                    container.appendChild(it);
                  }

                  insertTree(container, content, level + 1);
                  parent.appendChild(container);

                  folderEl.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const arrow = folderEl.querySelector(".freeapi-tree-folder-arrow");
                    const show = container.style.display === "none";
                    container.style.display = show ? "block" : "none";
                    arrow.textContent = show ? "▼" : "▶";
                  }, { passive: true });
                }
              };

              // 把目录结构追加到菜单 DOM
              insertTree(items[0]?.parentElement || added, folderMap);
            });
          }
        }
      });
      mutationObserver.observe(document.body, { childList: true, subtree: false });
    },
    nodeCreated(node) {
      if (!isTargetNode(node)) return;
      const w = getRoleWidget(node);
      if (!w) return;
      const ok = patchComboWidget(w);
      if (ok) {
        try { node.setDirtyCanvas(true, true); } catch (_) {}
      }
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
      try {
        const protoOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
          if (typeof protoOnNodeCreated === "function") {
            protoOnNodeCreated.apply(this, arguments);
          }
          if (isTargetNode(this)) {
            const w = getRoleWidget(this);
            if (w) patchComboWidget(w);
          }
        };
      } catch (e) {
        warn("beforeRegisterNodeDef hook failed:", e);
      }
    },
  });
})();