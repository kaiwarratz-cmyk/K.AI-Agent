const providerEl = document.getElementById("provider");
          const modelEl = document.getElementById("model");
          const roleEl = document.getElementById("role");
          const execModeEl = document.getElementById("execMode");
          const timeoutMaxStepEl = document.getElementById("timeoutMaxStep");
          const timeoutLlmApiEl = document.getElementById("timeoutLlmApi");
          const timeoutExecPlaneEl = document.getElementById("timeoutExecPlane");
          const toolOutputCapCharsEl = document.getElementById("toolOutputCapChars");
          const applyTimeoutsBtn = document.getElementById("applyTimeouts");
          const execShowConsoleEl = document.getElementById("execShowConsole");
          const execPlaneStatusEl = document.getElementById("execPlaneStatus");
          const workspaceInputEl = document.getElementById("workspaceInput");
          const fullAccessEl = document.getElementById("fullAccess");
          const deleteToTrashEl = document.getElementById("deleteToTrash");
          const llmTempEl = document.getElementById("llmTemp");
          const ollamaEnabledEl = document.getElementById("ollamaEnabled");
          const ollamaBaseUrlEl = document.getElementById("ollamaBaseUrl");
          const mcpTimeoutInputEl = document.getElementById("mcpTimeoutInput");
          const mcpCacheTtlInputEl = document.getElementById("mcpCacheTtlInput");
          const mcpLocalEnabledEl = document.getElementById("mcpLocalEnabled");
                              const siEnabledEl = document.getElementById("siEnabled");
          const siAutoExecuteEl = document.getElementById("siAutoExecute");
          const siScanIntervalEl = document.getElementById("siScanInterval");
          const siDeepIntervalEl = document.getElementById("siDeepInterval");
          const siCooldownEl = document.getElementById("siCooldown");
          const audioEnabledEl = document.getElementById("audioEnabled");
          const audioVoiceEl = document.getElementById("audioVoice");
          const audioModeEl = document.getElementById("audioMode");
          const quietModeEl = document.getElementById("quietMode");
          const showThinkingEl = document.getElementById("showThinking");
          const showActionsEl = document.getElementById("showActions");
          const cronActiveOnlyEl = document.getElementById("cronActiveOnly");
          const cronJobsListEl = document.getElementById("cronJobsList");
          const refreshSkillsEl = document.getElementById("refreshSkills");
          const skillsListEl = document.getElementById("skillsList");
          const promptEl = document.getElementById("prompt");
          const chatLogEl = document.getElementById("chatLog");
          const metaEl = document.getElementById("meta");
          const toolLogEl = document.getElementById("toolLog");
          const auditLogEl = document.getElementById("auditLog");
          const auditMetaEl = document.getElementById("auditMeta");
          const auditLimitEl = document.getElementById("auditLimit");
          const auditStageEl = document.getElementById("auditStage");
          const auditTraceIdEl = document.getElementById("auditTraceId");
          const testOutputEl = document.getElementById("testOutput");
          const configViewEl = document.getElementById("configView");
          const configRawEl = document.getElementById("configRaw");
          const secretAliasEl = document.getElementById("secretAlias");
          const secretValueEl = document.getElementById("secretValue");
          const secretAliasesEl = document.getElementById("secretAliases");
          const secretStatusEl = document.getElementById("secretStatus");
          const simulateInputEl = document.getElementById("simulateInput");
          const simulateRunEl = document.getElementById("simulateRun");
          const simulateOutputEl = document.getElementById("simulateOutput");
          let lastMeta = null;
          let lastNotificationId = 0;
          const sendBtn = document.getElementById("sendBtn");
          const STREAM_CHARS_PER_TICK = 2;
          const STREAM_TICK_MS = 22;
          let catalog = { providers: [] };
          const FIELD_HINTS = {
            provider: "LLM-Provider (API/Backend), aus dem Modelle geladen werden.",
            model: "Aktives LLM-Modell fuer Antworten und Tool-Planung.",
            llmTemp: "Temperatur: niedrig = stabiler, hoch = variabler.",
            applyLlm: "Speichert Provider, Modell und Temperatur.",
            refreshLlmCatalog: "Laedt Provider/Modelle neu aus den konfigurierten Quellen.",
            ollamaEnabled: "Aktiviert den Ollama-Provider (kein API-Key).",
            ollamaBaseUrl: "Basis-URL fuer Ollama, z. B. http://192.168.1.50:11434/v1",
            applyOllama: "Speichert die Ollama-Einstellungen.",
            role: "Rolle fuer Berechtigungen. admin erlaubt erweiterte Aktionen.",
            execMode: "Script-Ausfuehrung: deny blockiert, unrestricted erlaubt direkte Runs.",
            scriptTimeout: "Globales Timeout fuer script_exec in Sekunden.",
            applySecurity: "Speichert Sicherheits- und Script-Ausfuehrungsoptionen.",
            execShowConsole: "Steuert, ob die Execution-Plane mit sichtbarer Konsole startet.",
            applyExecutionPlane: "Speichert die Execution-Plane-Konfiguration.",
            reloadExecutionPlane: "Startet die Execution-Plane manuell neu.",
            resetSessionUi: "Setzt nur die aktuelle WebUI-Session zurueck.",
            workspaceInput: "Standard-Arbeitsverzeichnis fuer relative Dateioperationen.",
            fullAccess: "Wenn true: lockert Dateisystem-Grenzen fuer Aktionen.",
            deleteToTrash: "Wenn true: loeschen zuerst in Papierkorb statt direkt final.",
            applyFilesystem: "Speichert Dateisystem- und Workspace-Einstellungen.",
            siEnabled: "Aktiviert/deaktiviert den Self-Improve-Dienst.",
            siAutoExecute: "Wenn true: erkannte Fixes koennen automatisch angewandt werden.",
            siScanInterval: "Intervall fuer kleine, schnelle Self-Improve-Scans.",
            siDeepInterval: "Intervall fuer tiefere, langsamere Self-Improve-Analysen.",
            siCooldown: "Mindestabstand zwischen Self-Improve-Laeufen.",
            applySelfImprove: "Speichert alle Self-Improve-Einstellungen.",
            audioEnabled: "Globale Aktivierung fuer TTS-Antworten.",
            audioVoice: "Stimme fuer Audioausgabe.",
            audioMode: "Antwortmodus: Audioausgabe oder nur Text.",
            refreshAudioVoices: "Laedt die Liste verfuegbarer Stimmen neu.",
            applyAudio: "Speichert Audio/TTS-Einstellungen.",
            quietMode: "Reduziert Zwischenmeldungen; Fokus auf Endergebnis.",
            showThinking: "Zeigt/versteckt Denk-Ausgaben im UI.",
            showActions: "Zeigt/versteckt Tool-Aktionen im UI.",
            applyUiOptions: "Speichert UI-Anzeigeoptionen.",
            reactRetryEnabled: "Aktiviert automatische Neuversuche bei fehlgeschlagenen Plaenen.",
            reactMaxRetries: "Maximale Anzahl automatischer Wiederholungsversuche.",
            applyReactRetryOptions: "Speichert Retry-Einstellungen.",
            reactUseLoop: "Neuer ReAct-Loop mit Schritt-fuer-Schritt Feedback.",
            reactMaxIterations: "Maximale Anzahl Agent-Schritte pro Auftrag.",
            applyReactLoopOptions: "Speichert Loop-Einstellungen.",
            cronActiveOnly: "Filtert Anzeige auf aktive Cron-Jobs.",
            refreshCronJobs: "Laedt Cron-Job-Liste neu.",
            secretAlias: "Aliasname fuer ein Secret (z. B. token_xyz).",
            secretValue: "Geheimer Wert, wird nicht im Klartext angezeigt.",
            saveSecretBtn: "Speichert oder aktualisiert Secret unter Alias.",
            deleteSecretBtn: "Entfernt das Secret fuer den angegebenen Alias.",
            refreshSecretsBtn: "Aktualisiert die Alias-Liste.",
            mcpToolsSearch: "Filtert MCP-Tools nach Name, Beschreibung oder Server.",
            mcpToolsType: "Filter: alle, nur lokale dynamic-MCP oder externe MCP-Tools.",
            mcpToolsSort: "Sortierung der MCP-Tool-Liste.",
            mcpToolsRefreshBtn: "Fragt MCP-Server neu ab und aktualisiert Cache/Anzeige.",
            mcpRegistryQuery: "Suchbegriff fuer MCP-Registry-Recherche.",
            mcpRegistrySearchBtn: "Startet Suche in den konfigurierten MCP-Quellen.",
            mcpSourceId: "Eindeutige interne ID fuer eine MCP-Quelle.",
            mcpSourceType: "Quelltyp bestimmt Parser/Suchlogik (Registry/GitHub).",
            mcpSourceName: "Optionaler Anzeigename der Quelle.",
            mcpSourceBaseUrl: "Basis-URL der Registry/Quelle.",
            mcpSourceEnabled: "Aktiviert oder deaktiviert diese Quelle.",
            mcpSourceSaveBtn: "Speichert Quelle fuer Registry-Suche.",
            mcpSourceReloadBtn: "Laedt Quellliste neu.",
            toolTreeReloadBtn: "Laedt Tool-Register-Baum manuell neu (inkl. optional MCP-Refresh).",
            mcpTimeoutInput: "Timeout pro MCP-Tool-Aufruf in Sekunden.",
            mcpCacheTtlInput: "Cache-Lebensdauer fuer MCP-Toollisten in Sekunden.",
            mcpLocalEnabled: "Aktiviert lokalen MCP-Server (local_dynamic).",
            applyMcp: "Speichert MCP-Laufzeitoptionen."
          };
          const RISK_RULES = [
            {
              id: "execMode",
              level: "high",
              text: "Risiko hoch",
              isRisky: (el) => String(el.value || "") === "unrestricted",
            },
            {
              id: "fullAccess",
              level: "high",
              text: "Risiko hoch",
              isRisky: (el) => String(el.value || "") === "true",
            },
            {
              id: "siAutoExecute",
              level: "high",
              text: "Risiko hoch",
              isRisky: (el) => String(el.value || "") === "true",
            },
            {
              id: "deleteToTrash",
              level: "medium",
              text: "Risiko mittel",
              isRisky: (el) => String(el.value || "") === "false",
            },
            {
              id: "role",
              level: "medium",
              text: "Risiko mittel",
              isRisky: (el) => String(el.value || "") === "admin",
            },
            {
              id: "reactMaxIterations",
              level: "low",
              text: "Mehr Last",
              isRisky: (el) => Number(el.value || 0) >= 25,
            },
            {
              id: "reactMaxRetries",
              level: "low",
              text: "Mehr Last",
              isRisky: (el) => Number(el.value || 0) >= 5,
            },
          ];

          function _findLabelForInput(id, el) {
            const byFor = document.querySelector(`label[for="${id}"]`);
            if (byFor) return byFor;
            const wrap = el ? el.closest("div") : null;
            if (!wrap) return null;
            return wrap.querySelector("label");
          }

          function applyRiskHighlights() {
            const classByLevel = {
              high: "control-risk-high",
              medium: "control-risk-medium",
              low: "control-risk-low",
            };
            RISK_RULES.forEach((rule) => {
              const el = document.getElementById(rule.id);
              if (!el) return;
              Object.values(classByLevel).forEach((cls) => el.classList.remove(cls));
              const risky = Boolean(typeof rule.isRisky === "function" ? rule.isRisky(el) : false);
              if (risky && classByLevel[rule.level]) {
                el.classList.add(classByLevel[rule.level]);
              }

              const label = _findLabelForInput(rule.id, el);
              if (!label) return;
              label.classList.add("label-with-hint");
              let badge = label.querySelector(`.risk-tag[data-risk-for="${rule.id}"]`);
              if (!badge) {
                badge = document.createElement("span");
                badge.className = "risk-tag";
                badge.setAttribute("data-risk-for", rule.id);
                label.appendChild(badge);
              }
              if (risky) {
                badge.className = `risk-tag ${rule.level}`;
                badge.textContent = String(rule.text || "Risiko");
                badge.style.display = "inline-flex";
              } else {
                badge.className = "risk-tag";
                badge.textContent = "";
                badge.style.display = "none";
              }
            });
          }

          function bindRiskListeners() {
            if (window.__riskListenersBound) return;
            RISK_RULES.forEach((rule) => {
              const el = document.getElementById(rule.id);
              if (!el) return;
              el.addEventListener("change", applyRiskHighlights);
              el.addEventListener("input", applyRiskHighlights);
            });
            window.__riskListenersBound = true;
          }

          function applyFieldHints() {
            const closeHintPopovers = (except = null) => {
              document.querySelectorAll(".hint-icon.open").forEach(btn => {
                if (except && btn === except) return;
                btn.classList.remove("open");
              });
            };
            Object.entries(FIELD_HINTS).forEach(([id, hint]) => {
              const el = document.getElementById(id);
              if (!el) return;
              el.setAttribute("title", String(hint || ""));
              el.setAttribute("data-hint", String(hint || ""));

              const tag = String(el.tagName || "").toUpperCase();
              const isField = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
              if (!isField) return;

              let label = null;
              const byFor = document.querySelector(`label[for="${id}"]`);
              if (byFor) {
                label = byFor;
              } else {
                const wrap = el.closest("div");
                if (wrap) label = wrap.querySelector("label");
              }
              if (!label) return;
              if (label.querySelector(`[data-hint-for="${id}"]`)) return;

              label.classList.add("label-with-hint");
              const hintBtn = document.createElement("button");
              hintBtn.type = "button";
              hintBtn.className = "hint-icon";
              hintBtn.textContent = "?";
              hintBtn.setAttribute("aria-label", `Hinweis zu ${id}`);
              hintBtn.setAttribute("data-hint", String(hint || ""));
              hintBtn.setAttribute("data-hint-for", id);
              hintBtn.addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                const isOpen = hintBtn.classList.contains("open");
                closeHintPopovers();
                if (!isOpen) hintBtn.classList.add("open");
              });
              label.appendChild(hintBtn);
            });

            if (!window.__hintPopoverListenersBound) {
              document.addEventListener("click", () => closeHintPopovers());
              document.addEventListener("keydown", (ev) => {
                if (ev.key === "Escape") closeHintPopovers();
              });
              window.__hintPopoverListenersBound = true;
            }
            bindRiskListeners();
            applyRiskHighlights();
          }

          function modeLabel(mode) {
            if (mode === "deny") return "Blockieren (deny)";
            if (mode === "unrestricted") return "Direkt ausfuehren (unrestricted)";
            return String(mode || "");
          }

          function switchTab(name) {
            document.querySelectorAll(".tab-btn").forEach(btn => {
              btn.classList.toggle("active", btn.dataset.tab === name);
            });
            document.querySelectorAll(".panel").forEach(panel => {
              panel.classList.toggle("active", panel.id === `panel-${name}`);
            });
            if (name === "mcp") { mcpToolsLoad(); }
          }
          document.querySelectorAll(".tab-btn").forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

          function parsePythonRuntimeError(text) {
            const raw = String(text || "");
            if (!raw.includes("status=python_runtime_error")) return null;
            const lines = raw.split(/\r?\n/);
            const findValue = (prefix) => {
              const line = lines.find(l => l.toLowerCase().startsWith(prefix.toLowerCase()));
              if (!line) return "";
              const idx = line.indexOf(":");
              if (idx >= 0) return line.slice(idx + 1).trim();
              const eq = line.indexOf("=");
              return eq >= 0 ? line.slice(eq + 1).trim() : "";
            };
            const rcLine = lines.find(l => l.toLowerCase().startsWith("returncode=")) || "";
            const returncode = rcLine ? rcLine.split("=", 2)[1].trim() : "";
            const error = findValue("fehler:");
            const location = findValue("ort:");
            const detailHint = findValue("details:");
            const stdoutIdx = lines.findIndex(l => l.toLowerCase().startsWith("stdout (gekuerzt):"));
            let stdoutPreview = "";
            if (stdoutIdx >= 0) {
              stdoutPreview = lines.slice(stdoutIdx + 1).join("\n").trim();
            }
            return { returncode, error, location, detailHint, stdoutPreview, raw };
          }

          function normalizeDisplayText(value) {
            const src = String(value ?? "");
            if (!src) return "";
            // Heuristic for mojibake like "Ã¤", "Ã¶", "â€“".
            if (!/[Ãâ]/.test(src)) return src;
            try {
              const bytes = new Uint8Array(Array.from(src).map(ch => ch.charCodeAt(0) & 0xff));
              const repaired = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
              if (repaired && repaired !== src) {
                const umlautScore = (repaired.match(/[äöüÄÖÜß]/g) || []).length;
                const mojibakeScore = (src.match(/[Ãâ]/g) || []).length;
                if (umlautScore > 0 || mojibakeScore >= 2) return repaired;
              }
            } catch (_) {
              // fall back to replacements
            }
            return src
              .replace(/Ã¤/g, "ä")
              .replace(/Ã¶/g, "ö")
              .replace(/Ã¼/g, "ü")
              .replace(/Ã„/g, "Ä")
              .replace(/Ã–/g, "Ö")
              .replace(/Ãœ/g, "Ü")
              .replace(/ÃŸ/g, "ß")
              .replace(/â€“/g, "–")
              .replace(/â€”/g, "—")
              .replace(/â€ž/g, "„")
              .replace(/â€œ/g, "“")
              .replace(/â€˜/g, "‘")
              .replace(/â€™/g, "’")
              .replace(/â€¦/g, "…");
          }

          function formatDateTimeReadable(value, fallback = "-") {
            const src = String(value ?? "").trim();
            if (!src) return fallback;
            const ts = Date.parse(src);
            if (!Number.isFinite(ts)) return normalizeDisplayText(src);
            const dt = new Date(ts);
            const base = new Intl.DateTimeFormat("de-DE", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            }).format(dt);
            const offMin = -dt.getTimezoneOffset();
            const sign = offMin >= 0 ? "+" : "-";
            const abs = Math.abs(offMin);
            const hh = String(Math.floor(abs / 60)).padStart(2, "0");
            const mm = String(abs % 60).padStart(2, "0");
            return `${base} (UTC${sign}${hh}:${mm})`;
          }

          function appendInlineText(container, text) {
            const src = normalizeDisplayText(String(text || ""));
            const regex = /`([^`]+)`/g;
            let pos = 0;
            let m = null;
            while ((m = regex.exec(src)) !== null) {
              if (m.index > pos) {
                container.appendChild(document.createTextNode(src.slice(pos, m.index)));
              }
              const code = document.createElement("code");
              code.textContent = m[1];
              container.appendChild(code);
              pos = m.index + m[0].length;
            }
            if (pos < src.length) {
              container.appendChild(document.createTextNode(src.slice(pos)));
            }
          }

          function renderStructuredText(container, text) {
            container.innerHTML = "";
            const lines = normalizeDisplayText(String(text || "")).replace(/\r\n/g, "\n").split("\n");
            let i = 0;
            while (i < lines.length) {
              const line = lines[i];
              const fenced = line.match(/^```([a-zA-Z0-9_-]+)?\s*$/);
              if (fenced) {
                const lang = fenced[1] || "";
                const codeLines = [];
                i += 1;
                while (i < lines.length && !/^```/.test(lines[i])) {
                  codeLines.push(lines[i]);
                  i += 1;
                }
                if (i < lines.length && /^```/.test(lines[i])) i += 1;
                const pre = document.createElement("pre");
                pre.className = "msg-pre";
                const code = document.createElement("code");
                if (lang) code.dataset.lang = lang;
                code.textContent = codeLines.join("\n");
                pre.appendChild(code);
                container.appendChild(pre);
                continue;
              }

              if (/^\s*[-*]\s+/.test(line)) {
                const ul = document.createElement("ul");
                while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
                  const li = document.createElement("li");
                  appendInlineText(li, lines[i].replace(/^\s*[-*]\s+/, ""));
                  ul.appendChild(li);
                  i += 1;
                }
                container.appendChild(ul);
                continue;
              }

              if (/^\s*\d+\.\s+/.test(line)) {
                const ol = document.createElement("ol");
                while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                  const li = document.createElement("li");
                  appendInlineText(li, lines[i].replace(/^\s*\d+\.\s+/, ""));
                  ol.appendChild(li);
                  i += 1;
                }
                container.appendChild(ol);
                continue;
              }

              if (!line.trim()) {
                i += 1;
                continue;
              }

              const p = document.createElement("p");
              appendInlineText(p, line);
              container.appendChild(p);
              i += 1;
            }
            if (!container.childNodes.length) {
              const p = document.createElement("p");
              p.textContent = "";
              container.appendChild(p);
            }
          }

          function appendMsg(kind, text) {
            const div = document.createElement("div");
            div.className = `msg ${kind}`;
            if (kind === "bot") {
              const parsed = parsePythonRuntimeError(text);
              if (parsed) {
                const head = document.createElement("div");
                head.className = "msg-head";
                head.textContent = "Python Runtime-Fehler";
                const openToolsBtn = document.createElement("button");
                openToolsBtn.className = "secondary inline-btn";
                openToolsBtn.textContent = "Tool-Log";
                openToolsBtn.addEventListener("click", async () => {
                  await loadToolLog();
                  switchTab("tools");
                });
                head.appendChild(openToolsBtn);
                div.appendChild(head);

                if (parsed.error) {
                  const row = document.createElement("div");
                  row.className = "msg-kv";
                  row.innerHTML = `<strong>Fehler:</strong> ${parsed.error}`;
                  div.appendChild(row);
                }
                if (parsed.returncode) {
                  const row = document.createElement("div");
                  row.className = "msg-kv";
                  row.innerHTML = `<strong>Returncode:</strong> ${parsed.returncode}`;
                  div.appendChild(row);
                }
                if (parsed.location) {
                  const row = document.createElement("div");
                  row.className = "msg-kv";
                  row.innerHTML = `<strong>Ort:</strong> ${parsed.location}`;
                  div.appendChild(row);
                }

                const details = document.createElement("details");
                details.style.marginTop = "8px";
                const summary = document.createElement("summary");
                summary.textContent = "Details anzeigen";
                details.appendChild(summary);
                const pre = document.createElement("pre");
                pre.className = "msg-pre";
                pre.textContent = parsed.stdoutPreview || parsed.raw;
                details.appendChild(pre);
                div.appendChild(details);

                if (parsed.detailHint) {
                  const hint = document.createElement("div");
                  hint.className = "muted";
                  hint.style.marginTop = "6px";
                  hint.textContent = `Hinweis: ${parsed.detailHint}`;
                  div.appendChild(hint);
                }
              } else {
                const body = document.createElement("div");
                body.className = "msg-body";
                renderStructuredText(body, text);
                div.appendChild(body);
              }
            } else {
              const body = document.createElement("div");
              body.className = "msg-body";
              renderStructuredText(body, text);
              div.appendChild(body);
            }
            chatLogEl.appendChild(div);
            chatLogEl.scrollTop = chatLogEl.scrollHeight;
            return div;
          }

          function renderModels() {
            const providerId = providerEl.value;
            const p = catalog.providers.find(x => x.id === providerId);
            modelEl.innerHTML = "";
            if (!p) return;
            if (!p.api_key_set) return;
            p.models.forEach(m => {
              const opt = document.createElement("option");
              opt.value = m;
              opt.textContent = m;
              modelEl.appendChild(opt);
            });
          }

          function noCacheUrl(url) {
            const sep = url.includes("?") ? "&" : "?";
            return `${url}${sep}_ts=${Date.now()}`;
          }

          async function loadMeta() {
            const res = await fetch(noCacheUrl("/api/meta"), { cache: "no-store" });
            const data = await res.json();
            roleEl.value = data.active_role || "user";
            const mode = String(data.execution_mode || "unrestricted");
            execModeEl.value = ["deny", "unrestricted"].includes(mode) ? mode : "unrestricted";
            applyRiskHighlights();
            return data;
          }

          async function refreshExecutionPlaneStatus() {
            try {
              const res = await fetch("/api/execution/status");
              const data = await res.json();
              if (!res.ok || !data.ok) {
                execPlaneStatusEl.textContent = normalizeDisplayText("Status konnte nicht geladen werden.");
                return;
              }
              const cfg = data.config || {};
              const runtime = data.runtime || {};
              const stats = data.stats || {};
              const health = data.health || {};
              const runningCount = Number(stats.running_count || 0);
              const pid = Number(health.pid || runtime.pid || 0);
              const enabled = Boolean(data.enabled);
              const healthy = Boolean(health.ok);
              execPlaneStatusEl.textContent = normalizeDisplayText(
                `enabled=${enabled} | healthy=${healthy} | pid=${pid || "-"} | running_jobs=${runningCount} | show_console=${Boolean(cfg.show_console)}`
              );
            } catch (err) {
              execPlaneStatusEl.textContent = normalizeDisplayText(`Status-Fehler: ${err.message || err}`);
            }
          }

          async function loadLlmStatus() {
            try {
              const res = await fetch("/api/tests/llm?live=false");
              const data = await res.json();
              return { ok: Boolean(data.ok) };
            } catch {
              return { ok: false };
            }
          }

          function countdownText(iso) {
            const ts = Date.parse(String(iso || ""));
            if (!Number.isFinite(ts)) return "--:--";
            const diff = Math.max(0, Math.floor((ts - Date.now()) / 1000));
            const mm = Math.floor(diff / 60);
            const ss = diff % 60;
            return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
          }

          function renderMetaLine() {
            if (!lastMeta) return;
            const meta = lastMeta.meta || {};
            const llm = lastMeta.llm || { ok: false };
            const si = meta.self_improve || {};
            const siTxt = si.enabled
              ? `Self-Improve: klein in ${countdownText(si.next_scan_at)} | gross in ${countdownText(si.next_deep_at)}`
              : "Self-Improve: AUS";
            const targetEl = document.getElementById('metaInfo') || metaEl;
            if (targetEl) {
              targetEl.textContent = normalizeDisplayText(
                `Admin Prozess: ${meta.admin_process ? "JA" : "NEIN"} | Rolle: ${meta.active_role} | Modus: ${modeLabel(meta.execution_mode)} | LLM: ${meta.active_provider_id}/${meta.active_model} | LLM-Konfiguration: ${llm.ok ? "OK" : "FEHLT"} | ${siTxt}`
              );
            }
          }

          async function refreshMetaLine() {
            const [meta, llm] = await Promise.all([loadMeta(), loadLlmStatus()]);
            lastMeta = { meta, llm };
            renderMetaLine();
          }

          async function loadCatalog() {
            const res = await fetch(noCacheUrl("/api/catalog"), { cache: "no-store" });
            catalog = await res.json();
            providerEl.innerHTML = "";
            let firstAllowed = "";
            (catalog.providers || []).forEach(p => {
              const opt = document.createElement("option");
              opt.value = p.id;
              const hasKey = Boolean(p.api_key_set);
              opt.textContent = hasKey ? `${p.name} (${p.id})` : `${p.name} (${p.id}) [kein API-Key]`;
              opt.disabled = !hasKey;
              if (!firstAllowed && hasKey) firstAllowed = p.id;
              providerEl.appendChild(opt);
            });
            if (firstAllowed) {
              providerEl.value = firstAllowed;
            }
            renderModels();
            applyRiskHighlights();
          }

          async function loadToolLog() {
            const res = await fetch("/api/tool_log");
            const data = await res.json();
            toolLogEl.innerHTML = "";
            data.items.forEach(item => {
              const div = document.createElement("div");
              div.className = "item";
              const created = formatDateTimeReadable(item.created_at, "");
              div.textContent = normalizeDisplayText(`[${created}] ${item.tool}: ${item.note}`);
              toolLogEl.appendChild(div);
            });
          }

          async function cronJobAction(action, jobId) {
            const res = await fetch(`/api/cron/jobs/${action}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ job_id: jobId })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok) {
              appendMsg("bot", `Cron-Job ${action} fehlgeschlagen: ${normalizeDisplayText(String(data.detail || data.reply || "unbekannt"))}`);
              return false;
            }
            appendMsg("bot", normalizeDisplayText(String(data.reply || `Cron-Job ${action} erfolgreich.`)));
            await loadToolLog();
            return true;
          }

          async function loadCronJobs() {
            const activeOnly = cronActiveOnlyEl.value === "true";
            const res = await fetch(`/api/cron/jobs?active_only=${activeOnly ? "true" : "false"}`);
            const data = await res.json().catch(() => ({}));
            cronJobsListEl.innerHTML = "";
            const items = Array.isArray(data.items) ? data.items : [];
            if (!items.length) {
              const div = document.createElement("div");
              div.className = "item";
              div.textContent = "Keine Cron-Jobs vorhanden.";
              cronJobsListEl.appendChild(div);
              return;
            }
            items.forEach(item => {
              const row = document.createElement("div");
              row.className = "item";
              const id = String(item.id || "");
              const enabled = Boolean(item.enabled);
              const schedule = String(
                item.schedule
                || (item.interval_sec ? `alle ${item.interval_sec}s` : (item.run_at ? `einmalig: ${formatDateTimeReadable(item.run_at)}` : "-"))
              );
              const nextRun = formatDateTimeReadable(item.next_run_at);
              const task = String(item.task || "-");
              const head = document.createElement("div");
              head.innerHTML = `<strong>${normalizeDisplayText(id)}</strong> <span class="${enabled ? "v-ok" : "v-bad"}">${enabled ? "aktiv" : "pausiert"}</span>`;
              const meta = document.createElement("div");
              meta.className = "muted";
              meta.textContent = normalizeDisplayText(`schedule=${schedule} | next=${nextRun}`);
              const taskDiv = document.createElement("div");
              taskDiv.textContent = normalizeDisplayText(task);
              const actions = document.createElement("div");
              actions.className = "action-grid";
              actions.style.marginTop = "6px";

              const pauseBtn = document.createElement("button");
              pauseBtn.className = "ghost";
              pauseBtn.textContent = "Pausieren";
              pauseBtn.disabled = !enabled;
              pauseBtn.addEventListener("click", async () => {
                const ok = await cronJobAction("pause", id);
                if (ok) await loadCronJobs();
              });

              const resumeBtn = document.createElement("button");
              resumeBtn.className = "secondary";
              resumeBtn.textContent = "Fortsetzen";
              resumeBtn.disabled = enabled;
              resumeBtn.addEventListener("click", async () => {
                const ok = await cronJobAction("resume", id);
                if (ok) await loadCronJobs();
              });

              const testBtn = document.createElement("button");
              testBtn.className = "ghost";
              testBtn.textContent = "Testen";
              testBtn.addEventListener("click", async () => {
                const ok = await cronJobAction("test", id);
                if (ok) await loadCronJobs();
              });

              const deleteBtn = document.createElement("button");
              deleteBtn.className = "ghost";
              deleteBtn.textContent = "Loeschen";
              deleteBtn.addEventListener("click", async () => {
                const yes = confirm(`Cron-Job wirklich loeschen? ${id}`);
                if (!yes) return;
                const ok = await cronJobAction("delete", id);
                if (ok) await loadCronJobs();
              });

              actions.appendChild(pauseBtn);
              actions.appendChild(resumeBtn);
              actions.appendChild(testBtn);
              actions.appendChild(deleteBtn);
              row.appendChild(head);
              row.appendChild(meta);
              row.appendChild(taskDiv);
              row.appendChild(actions);
              cronJobsListEl.appendChild(row);
            });
          }

          async function skillToggle(skillId, enabled) {
            const res = await fetch("/api/skills/enable", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ skill_id: skillId, enabled: Boolean(enabled) })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok) {
              appendMsg("bot", `Skill-Update fehlgeschlagen: ${normalizeDisplayText(String(data.detail || "unbekannt"))}`);
              return false;
            }
            appendMsg("bot", normalizeDisplayText(`Skill ${enabled ? "aktiviert" : "deaktiviert"}: ${skillId}`));
            return true;
          }

          async function setSkillSecret(skillId, sec) {
            const alias = String(sec.alias || "").trim();
            const label = String(sec.label || alias).trim();
            const desc = String(sec.description || "").trim();
            if (!alias) {
              appendMsg("bot", "Skill-Secret: Alias fehlt.");
              return;
            }
            const hint = desc ? `\n${desc}` : "";
            const value = prompt(`Secret setzen fuer ${skillId}\n${label} (${alias})${hint}\n\nAbbrechen = Verwerfen`, "");
            if (value === null) {
              appendMsg("bot", normalizeDisplayText(`Secret-Speichern verworfen: ${alias}`));
              return;
            }
            if (!String(value || "").trim()) {
              appendMsg("bot", normalizeDisplayText(`Leerer Secret-Wert fuer ${alias} ist nicht erlaubt.`));
              return;
            }
            const ok = confirm(`Secret ${alias} fuer Skill ${skillId} speichern?`);
            if (!ok) {
              appendMsg("bot", normalizeDisplayText(`Secret-Speichern verworfen: ${alias}`));
              return;
            }
            const res = await fetch("/api/skills/secret", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ skill_id: skillId, alias, value: String(value) })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok) {
              appendMsg("bot", `Skill-Secret speichern fehlgeschlagen (${normalizeDisplayText(alias)}): ${normalizeDisplayText(String(data.detail || "unbekannt"))}`);
              return;
            }
            appendMsg("bot", normalizeDisplayText(`Skill-Secret gespeichert: ${alias} (${skillId})`));
            await loadSkills();
            await loadSecrets();
          }

          async function loadSkills() {
            const res = await fetch("/api/skills");
            const data = await res.json().catch(() => ({}));
            skillsListEl.innerHTML = "";
            const items = Array.isArray(data.items) ? data.items : [];
            if (!items.length) {
              const div = document.createElement("div");
              div.className = "item";
              div.textContent = "Keine Skills gefunden.";
              skillsListEl.appendChild(div);
              return;
            }
            items.forEach((item, idx) => {
              const row = document.createElement("div");
              row.className = "item skill-card";
              if (idx % 2 === 1) {
                row.style.background = "#e7f2ff";
                row.style.borderColor = "#7ea5c4";
                row.style.borderLeft = "8px solid #2f6f9f";
              } else {
                row.style.background = "#fffdf6";
                row.style.borderColor = "#d1c39a";
                row.style.borderLeft = "8px solid #a57c1b";
              }
              const id = String(item.id || "");
              const name = String(item.name || id);
              const enabled = Boolean(item.enabled);
              const desc = String(item.description || "");
              const tools = Array.isArray(item.tools) ? item.tools : [];
              const secrets = Array.isArray(item.secrets) ? item.secrets : [];
              const missingRequired = Array.isArray(item.missing_required) ? item.missing_required : [];
              const canEnable = Boolean(item.can_enable);
              const head = document.createElement("div");
              head.className = "skill-headline";
              head.innerHTML = `<strong>${normalizeDisplayText(id)}</strong> <span class="${enabled ? "v-ok" : "v-bad"}">${enabled ? "aktiv" : "inaktiv"}</span> <span class="muted">${normalizeDisplayText(name)}</span>`;
              const meta = document.createElement("div");
              meta.className = "skill-subline";
              meta.textContent = normalizeDisplayText(`${desc || "-"} | tools=${tools.length} | secrets=${secrets.length}`);
              const sec = document.createElement("div");
              sec.className = "skill-subline";
              sec.textContent = missingRequired.length
                ? normalizeDisplayText(`Fehlende Pflicht-Secrets: ${missingRequired.join(", ")}`)
                : "Pflicht-Secrets: ok";
              const secList = document.createElement("div");
              secList.className = "list skill-secrets is-collapsed";
              secList.style.maxHeight = "170px";
              secList.style.marginTop = "6px";
              if (!secrets.length) {
                const empty = document.createElement("div");
                empty.className = "item";
                empty.textContent = "Keine Skill-Secrets deklariert.";
                secList.appendChild(empty);
              } else {
                secrets.forEach(secItem => {
                  const alias = String(secItem.alias || "").trim();
                  const label = String(secItem.label || alias).trim();
                  const isSet = Boolean(secItem.is_set);
                  const required = Boolean(secItem.required);
                  const descText = String(secItem.description || "").trim();
                  const secRow = document.createElement("div");
                  secRow.className = "item";
                  const secHead = document.createElement("div");
                  secHead.innerHTML = `<strong>${normalizeDisplayText(label)}</strong> <code>${normalizeDisplayText(alias)}</code> <span class="${isSet ? "v-ok" : "v-bad"}">${isSet ? "gesetzt" : "fehlt"}</span> <span class="muted">${required ? "required" : "optional"}</span>`;
                  const secDesc = document.createElement("div");
                  secDesc.className = "muted";
                  secDesc.textContent = normalizeDisplayText(descText || "-");
                  const secActions = document.createElement("div");
                  secActions.className = "action-grid";
                  secActions.style.marginTop = "4px";
                  const setBtn = document.createElement("button");
                  setBtn.className = "secondary";
                  setBtn.textContent = isSet ? "Secret aktualisieren" : "Secret setzen";
                  setBtn.addEventListener("click", async () => {
                    await setSkillSecret(id, secItem);
                  });
                  secActions.appendChild(setBtn);
                  secRow.appendChild(secHead);
                  secRow.appendChild(secDesc);
                  secRow.appendChild(secActions);
                  secList.appendChild(secRow);
                });
              }
              const actions = document.createElement("div");
              actions.className = "skill-actions";
              const toggleSecBtn = document.createElement("button");
              toggleSecBtn.className = "ghost";
              toggleSecBtn.textContent = "Secrets anzeigen";
              toggleSecBtn.addEventListener("click", () => {
                const collapsed = secList.classList.toggle("is-collapsed");
                toggleSecBtn.textContent = collapsed ? "Secrets anzeigen" : "Secrets ausblenden";
              });
              const enBtn = document.createElement("button");
              enBtn.className = "secondary";
              enBtn.textContent = canEnable ? "Aktivieren" : "Aktivieren (Secrets fehlen)";
              enBtn.disabled = enabled || !canEnable;
              enBtn.addEventListener("click", async () => {
                const ok = await skillToggle(id, true);
                if (ok) {
                  await loadSkills();
                  await loadConfigView();
                }
              });
              const disBtn = document.createElement("button");
              disBtn.className = "ghost";
              disBtn.textContent = "Deaktivieren";
              disBtn.disabled = !enabled;
              disBtn.addEventListener("click", async () => {
                const ok = await skillToggle(id, false);
                if (ok) {
                  await loadSkills();
                  await loadConfigView();
                }
              });
              actions.appendChild(toggleSecBtn);
              if (id.toLowerCase() === "gmail") {
                const connectBtn = document.createElement("button");
                connectBtn.className = "secondary";
                connectBtn.textContent = "Gmail verbinden";
                connectBtn.addEventListener("click", async () => {
                  const res = await fetch("/api/skills/gmail/connect/start");
                  const data = await res.json().catch(() => ({}));
                  if (!res.ok || !data.ok || !String(data.auth_url || "").trim()) {
                    appendMsg("bot", `Gmail Connect fehlgeschlagen: ${normalizeDisplayText(String(data.detail || "unbekannt"))}`);
                    return;
                  }
                  window.open(String(data.auth_url), "_blank", "noopener");
                  appendMsg("bot", "Gmail OAuth gestartet. Nach Freigabe werden die Tokens automatisch gespeichert.");
                });
                actions.appendChild(connectBtn);
              }
              actions.appendChild(enBtn);
              actions.appendChild(disBtn);
              row.appendChild(head);
              row.appendChild(meta);
              row.appendChild(sec);
              row.appendChild(secList);
              row.appendChild(actions);
              skillsListEl.appendChild(row);
            });
          }

          async function loadAuditLog() {
            const params = new URLSearchParams();
            params.set("limit", String(auditLimitEl.value || "200"));
            const stage = String(auditStageEl.value || "").trim();
            const traceId = String(auditTraceIdEl.value || "").trim();
            if (stage) params.set("stage", stage);
            if (traceId) params.set("trace_id", traceId);
            const res = await fetch(`/api/logs/audit?${params.toString()}`);
            const data = await res.json();
            auditLogEl.innerHTML = "";
            const pathTxt = normalizeDisplayText(String(data.path || ""));
            auditMetaEl.textContent = normalizeDisplayText(`Pfad: ${pathTxt} | Treffer: ${data.count || 0}`);
            (data.items || []).forEach(item => {
              const div = document.createElement("div");
              div.className = "item";
              const head = document.createElement("div");
              const ts = normalizeDisplayText(String(item.ts || ""));
              // Fix: API liefert 'kind' und 'message', nicht 'stage'/'payload'
              const kindTxt = normalizeDisplayText(String(item.kind || item.stage || ""));
              const traceTxt = normalizeDisplayText(String(item.trace_id || ""));
              const msgTxt = normalizeDisplayText(String(item.message || ""));
              head.innerHTML = `<strong>${ts}</strong> <code style="color:#22a2b5;">${kindTxt}</code> <span class="muted">trace=${traceTxt}</span>`;
              const pre = document.createElement("pre");
              pre.className = "msg-pre";
              // Zeige message direkt als Text, nur bei komplexem payload JSON
              if (msgTxt && msgTxt !== "{}") {
                pre.textContent = msgTxt;
              } else {
                const payloadObj = item.payload || {};
                const payloadKeys = Object.keys(payloadObj);
                if (payloadKeys.length > 0) {
                  pre.textContent = normalizeDisplayText(JSON.stringify(payloadObj, null, 2));
                } else {
                  pre.textContent = "(kein Inhalt)";
                }
              }
              div.appendChild(head);
              div.appendChild(pre);
              auditLogEl.appendChild(div);
            });

          }

          async function loadNotifications() {
            const res = await fetch(`/api/notifications?after_id=${encodeURIComponent(String(lastNotificationId || 0))}&limit=50`);
            const data = await res.json().catch(() => ({}));
            const items = Array.isArray(data.items) ? data.items : [];
            items.forEach(item => {
              const id = Number(item.id || 0);
              if (id > lastNotificationId) lastNotificationId = id;
              const txt = normalizeDisplayText(String(item.text || "").trim());
              if (!txt) return;
              appendMsg("bot", `[Cron][WebUI] ${txt}`);
            });
            const apiLast = Number(data.last_id || 0);
            if (apiLast > lastNotificationId) lastNotificationId = apiLast;
          }

          function appendTestOutput(title, payload, isError = false) {
            const div = document.createElement("div");
            div.className = "item";
            const when = new Date().toLocaleTimeString();
            const pre = document.createElement("pre");
            pre.className = "msg-pre";
            pre.style.marginTop = "6px";
            pre.textContent = normalizeDisplayText(
              typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)
            );
            const head = document.createElement("div");
            head.innerHTML = `<strong>${normalizeDisplayText(title)}</strong> <span class="muted">(${when})</span>`;
            if (isError) head.innerHTML += ` <span class="v-bad">FEHLER</span>`;
            div.appendChild(head);
            div.appendChild(pre);
            testOutputEl.prepend(div);
          }

          function cfgCard(title, rows) {
            const card = document.createElement("div");
            card.className = "cfg-card";
            const h = document.createElement("div");
            h.className = "cfg-title";
            h.textContent = normalizeDisplayText(title);
            card.appendChild(h);
            rows.forEach(([k, v, state]) => {
              const row = document.createElement("div");
              row.className = "kv";
              const key = document.createElement("div");
              key.className = "k";
              key.textContent = normalizeDisplayText(k);
              const val = document.createElement("div");
              val.textContent = normalizeDisplayText(v);
              if (state === "ok") val.className = "v-ok";
              if (state === "bad") val.className = "v-bad";
              row.appendChild(key);
              row.appendChild(val);
              card.appendChild(row);
            });
            return card;
          }

          function yn(flag) { return flag ? ["JA", "ok"] : ["NEIN", "bad"]; }

          async function loadConfigView() {
            const res = await fetch(noCacheUrl("/api/config"), { cache: "no-store" });
            const cfg = await res.json();
            configViewEl.innerHTML = "";
            configRawEl.textContent = normalizeDisplayText(JSON.stringify(cfg, null, 2));

            const [adminProc, adminState] = yn(false);
            const sec = cfg.security || {};
            const fs = cfg.filesystem || {};
            const llm = cfg.llm || {};
            const si = cfg.self_improve || {};
            const mcp = cfg.mcp || {};
            const ep = cfg.execution_plane || {};
            const toolsCfg = cfg.tools || {};
            const providers = cfg.providers || {};
            const messenger = cfg.messenger || {};

            const ollamaCfg = providers.ollama || {};
            if (ollamaEnabledEl) {
              ollamaEnabledEl.value = String(Boolean(ollamaCfg.enabled));
            }
            if (ollamaBaseUrlEl) {
              ollamaBaseUrlEl.value = String(ollamaCfg.base_url || "http://127.0.0.1:11434/v1");
            }

            workspaceInputEl.value = String(cfg.workspace || "");
            fullAccessEl.value = String(Boolean(fs.full_access));
            deleteToTrashEl.value = String(fs.delete_to_trash !== false);
            siEnabledEl.value = String(si.enabled !== false);
            siAutoExecuteEl.value = String(Boolean(si.auto_execute));
            siScanIntervalEl.value = String(si.scan_interval_sec ?? 300);
            siDeepIntervalEl.value = String(si.deep_check_interval_sec ?? 1800);
            siCooldownEl.value = String(si.cooldown_sec ?? 900);
            mcpTimeoutInputEl.value = String(mcp.timeout ?? 45);
            mcpCacheTtlInputEl.value = String(mcp.cache_ttl_sec ?? 300);
            mcpLocalEnabledEl.value = String(mcp.local_server_enabled !== false);
            execShowConsoleEl.value = String(Boolean(ep.show_console));
                                    await refreshExecutionPlaneStatus();

            const activeProvider = String(llm.active_provider_id || "");
            const activeModel = String(llm.active_model || "");
            if (activeProvider && Array.from(providerEl.options).some(o => o.value === activeProvider)) {
              providerEl.value = activeProvider;
              renderModels();
            }
            if (activeModel && Array.from(modelEl.options).some(o => o.value === activeModel)) {
              modelEl.value = activeModel;
            }
            llmTempEl.value = String(llm.temperature ?? 0.2);
            applyRiskHighlights();

            configViewEl.appendChild(cfgCard("Sicherheit", [
              ["Rolle", String(sec.active_role || "")],
              ["Own Script Run", modeLabel(String(sec.execution_mode || ""))],
              ["Admin Prozess (siehe Meta)", adminProc, adminState]
            ]));
            configViewEl.appendChild(cfgCard("Dateisystem", [
              ["Arbeitsverzeichnis", String(cfg.workspace || "")],
              ["full_access", String(fs.full_access)],
              ["delete_to_trash", String(fs.delete_to_trash !== false)]
            ]));
            configViewEl.appendChild(cfgCard("LLM Aktiv", [
              ["Provider", String(llm.active_provider_id || "")],
              ["Modell", String(llm.active_model || "")],
              ["Temperatur", String(llm.temperature ?? "")]
            ]));
            configViewEl.appendChild(cfgCard("MCP", [
              ["timeout", String(mcp.timeout ?? 45)],
              ["cache_ttl_sec", String(mcp.cache_ttl_sec ?? 300)],
              ["local_server_enabled", String(mcp.local_server_enabled !== false)]
            ]));
            configViewEl.appendChild(cfgCard("Execution-Plane", [
              ["enabled", String(ep.enabled !== false)],
              ["host", String(ep.host || "127.0.0.1")],
              ["port", String(ep.port ?? 8765)],
              ["show_console", String(Boolean(ep.show_console))]
            ]));
            
            Object.entries(providers).forEach(([name, p]) => {
              const [setTxt, setState] = yn(Boolean(p.api_key_set));
              configViewEl.appendChild(cfgCard(`Provider: ${name}`, [
                ["Typ", String(p.type || "")],
                ["Basis-URL", String(p.base_url || "")],
                ["Standardmodell", String(p.default_model || "")],
                ["API-Key gesetzt", setTxt, setState]
              ]));
            });

            const t = messenger.telegram || {};
            const d = messenger.discord || {};
            const [tgSet, tgState] = yn(Boolean(t.token_set));
            const [dcSet, dcState] = yn(Boolean(d.token_set));
            configViewEl.appendChild(cfgCard("Integrationen", [
              ["messenger.reply_timeout_sec", String(messenger.reply_timeout_sec ?? 600)],
              ["telegram.enabled", String(t.enabled)],
              ["telegram.token_set", tgSet, tgState],
              ["discord.enabled", String(d.enabled)],
              ["discord.token_set", dcSet, dcState]
            ]));
            configViewEl.appendChild(cfgCard("Self-Improve", [
              ["enabled", String(si.enabled !== false)],
              ["scan_interval_sec", String(si.scan_interval_sec ?? 300)],
              ["deep_check_interval_sec", String(si.deep_check_interval_sec ?? 1800)],
              ["cooldown_sec", String(si.cooldown_sec ?? 900)],
              ["auto_execute", String(Boolean(si.auto_execute))]
            ]));

            const tts = cfg.tts || {};
            configViewEl.appendChild(cfgCard("Audio (TTS)", [
              ["enabled", String(tts.enabled !== false)],
              ["voice", String(tts.voice || "de-DE-ConradNeural")],
              ["mode", String(tts.mode || "reply_audio")]
            ]));
          }

          async function loadSecrets() {
            const res = await fetch(noCacheUrl("/api/secrets"), { cache: "no-store" });
            const data = await res.json();
            secretAliasesEl.innerHTML = "";
            const items = Array.isArray(data.items) ? data.items : [];
            if (!items.length) {
              const div = document.createElement("div");
              div.className = "item";
              div.textContent = "Keine Secret-Aliase vorhanden.";
              secretAliasesEl.appendChild(div);
              secretStatusEl.textContent = "Secret-Store: 0 Aliase";
              return;
            }
            items.forEach(item => {
              const div = document.createElement("div");
              div.className = "item";
              const alias = normalizeDisplayText(String(item.alias || ""));
              const updated = normalizeDisplayText(formatDateTimeReadable(item.updated_at));
              const source = normalizeDisplayText(String(item.source || ""));
              div.innerHTML = `<strong>${alias}</strong><br><span class="muted">updated: ${updated} | source: ${source || "-"}</span>`;
              secretAliasesEl.appendChild(div);
            });
            secretStatusEl.textContent = normalizeDisplayText(`Secret-Store: ${items.length} Alias(e)`);
          }

          async function saveSecretWithConfirm(aliasRaw, valueRaw) {
            const alias = String(aliasRaw || "").trim();
            const value = String(valueRaw || "");
            if (!alias || !value) {
              appendMsg("bot", "Secret speichern: Alias und Wert sind erforderlich.");
              return;
            }
            const first = await fetch("/api/secrets/upsert", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ alias, value, confirm: false })
            });
            const d1 = await first.json().catch(() => ({}));
            if (!first.ok) {
              appendMsg("bot", `Secret speichern fehlgeschlagen: ${normalizeDisplayText(String(d1.detail || "unbekannt"))}`);
              return;
            }
            if (d1.needs_confirmation) {
              const ok = confirm(`Bestaetigen: ${String(d1.message || "Secret speichern/aktualisieren?")}`);
              if (!ok) {
                appendMsg("bot", "Secret-Speichern abgebrochen.");
                return;
              }
              const second = await fetch("/api/secrets/upsert", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ alias, value, confirm: true, confirm_alias: String(d1.alias || alias) })
              });
              const d2 = await second.json().catch(() => ({}));
              if (!second.ok || !d2.ok) {
                appendMsg("bot", `Secret speichern fehlgeschlagen: ${normalizeDisplayText(String(d2.detail || d2.message || "unbekannt"))}`);
                return;
              }
              appendMsg("bot", `Secret gespeichert: alias=${normalizeDisplayText(String(d2.alias || alias))}, fingerprint=${normalizeDisplayText(String(d2.fingerprint || ""))}`);
              secretValueEl.value = "";
              await loadSecrets();
              await loadToolLog();
            }
          }

          async function deleteSecretWithConfirm(aliasRaw) {
            const alias = String(aliasRaw || "").trim();
            if (!alias) {
              appendMsg("bot", "Secret loeschen: Alias ist erforderlich.");
              return;
            }
            const first = await fetch("/api/secrets/delete", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ alias, confirm: false })
            });
            const d1 = await first.json().catch(() => ({}));
            if (!first.ok) {
              appendMsg("bot", `Secret loeschen fehlgeschlagen: ${normalizeDisplayText(String(d1.detail || "unbekannt"))}`);
              return;
            }
            if (d1.not_found) {
              appendMsg("bot", `Secret-Alias nicht gefunden: ${normalizeDisplayText(String(d1.alias || alias))}`);
              return;
            }
            if (d1.needs_confirmation) {
              const ok = confirm(`Bestaetigen: ${String(d1.message || "Secret loeschen?")}`);
              if (!ok) {
                appendMsg("bot", "Secret-Loeschen abgebrochen.");
                return;
              }
              const second = await fetch("/api/secrets/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ alias, confirm: true, confirm_alias: String(d1.alias || alias) })
              });
              const d2 = await second.json().catch(() => ({}));
              if (!second.ok || !d2.ok) {
                appendMsg("bot", `Secret loeschen fehlgeschlagen: ${normalizeDisplayText(String(d2.detail || d2.message || "unbekannt"))}`);
                return;
              }
              appendMsg("bot", `Secret geloescht: alias=${normalizeDisplayText(String(d2.alias || alias))}`);
              await loadSecrets();
              await loadToolLog();
            }
          }

          async function postStreamMessage(message) {
            appendMsg("user", message);
            sendBtn.disabled = true;
            sendBtn.textContent = "Arbeitet...";
            // Typing-Bubble anzeigen
            const typingDiv = document.createElement("div");
            typingDiv.className = "msg bot";
            typingDiv.innerHTML = '<div class="typing-bubble"><span></span><span></span><span></span></div>';
            chatLogEl.appendChild(typingDiv);
            chatLogEl.scrollTop = chatLogEl.scrollHeight;
            try {
              const res = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message })
              });
              if (!res.ok || !res.body) throw new Error("Stream konnte nicht gestartet werden.");
              // Typing-Bubble durch echte Bot-Nachricht ersetzen
              typingDiv.remove();
              const botMsgEl = appendMsg("bot", "");
              const botBodyEl = botMsgEl.querySelector(".msg-body");
              const reader = res.body.getReader();
              const decoder = new TextDecoder();
              let buffer = "";
              let pendingText = "";
              let finalText = "";
              let streamHadError = false;
              let renderTimer = null;
              const startRenderer = () => {
                if (renderTimer) return;
                renderTimer = setInterval(() => {
                  if (!pendingText) return;
                  const part = pendingText.slice(0, STREAM_CHARS_PER_TICK);
                  pendingText = pendingText.slice(STREAM_CHARS_PER_TICK);
                  finalText += part;
                  if (botBodyEl) botBodyEl.textContent = finalText;
                  chatLogEl.scrollTop = chatLogEl.scrollHeight;
                }, STREAM_TICK_MS);
              };
              const stopRenderer = async () => {
                while (pendingText.length > 0) {
                  const part = pendingText.slice(0, STREAM_CHARS_PER_TICK);
                  pendingText = pendingText.slice(STREAM_CHARS_PER_TICK);
                  finalText += part;
                  if (botBodyEl) botBodyEl.textContent = finalText;
                }
                if (renderTimer) clearInterval(renderTimer);
                if (botBodyEl) renderStructuredText(botBodyEl, finalText);
              };
              startRenderer();
              while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split("\n\n");
                buffer = events.pop() || "";
                for (const event of events) {
                  const line = event.split("\n").find(l => l.startsWith("data: "));
                  if (!line) continue;
                  const payload = JSON.parse(line.slice(6));
                  if (payload.type === "chunk") pendingText += (payload.text || "");
                  if (payload.type === "error") {
                    streamHadError = true;
                    await stopRenderer();
                    if (botBodyEl) renderStructuredText(botBodyEl, payload.message || "LLM Fehler");
                    if (reader && typeof reader.cancel === "function") {
                      try { await reader.cancel(); } catch (_) { }
                    }
                    break;
                  }
                }
                if (streamHadError) break;
              }
              if (!streamHadError) {
                await stopRenderer();
              }
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              typingDiv.remove();
              appendMsg("bot", `Fehler: ${err.message || err}`);
            } finally {
              sendBtn.disabled = false;
              sendBtn.textContent = "Senden";
            }
          }

          sendBtn.addEventListener("click", async () => {
            const message = promptEl.value.trim();
            if (!message) return;
            promptEl.value = "";
            await postStreamMessage(message);
            promptEl.focus();
          });
          promptEl.addEventListener("keydown", async (ev) => {
            if (ev.key === "Enter" && !ev.shiftKey) {
              ev.preventDefault();
              if (!sendBtn.disabled) {
                sendBtn.click();
              }
            }
          });
          providerEl.addEventListener("change", renderModels);

          document.getElementById("applyLlm").addEventListener("click", async () => {
            const p = (catalog.providers || []).find(x => x.id === providerEl.value);
            if (!p || !Boolean(p.api_key_set)) {
              appendMsg("bot", "LLM-Konfiguration nicht gespeichert: fuer den gewaehlten Provider fehlt ein API-Key im Setup.");
              return;
            }
            if (!modelEl.value) {
              appendMsg("bot", "LLM-Konfiguration nicht gespeichert: kein Modell ausgewaehlt/freigeschaltet.");
              return;
            }
            const temp = Number(llmTempEl.value || 0.2);
            const res = await fetch("/api/config/llm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                provider_id: providerEl.value,
                model: modelEl.value,
                temperature: Number.isFinite(temp) ? temp : 0.2
              })
            });
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              appendMsg("bot", `LLM-Konfiguration fehlgeschlagen: ${data.detail || "unbekannt"}`);
              return;
            }
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
            appendMsg("bot", "LLM-Konfiguration gespeichert.");
          });
          document.getElementById("applyOllama").addEventListener("click", async () => {
            const res = await fetch("/api/config/provider", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                provider_id: "ollama",
                enabled: ollamaEnabledEl.value === "true",
                base_url: String(ollamaBaseUrlEl.value || "").trim()
              })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
              appendMsg("bot", `Ollama-Konfiguration fehlgeschlagen: ${data.detail || "unbekannt"}`);
              return;
            }
            await loadToolLog();
            await loadCatalog();
            await loadConfigView();
            await refreshMetaLine();
            appendMsg("bot", "Ollama-Konfiguration gespeichert.");
          });
          document.getElementById("refreshLlmCatalog").addEventListener("click", async () => {
            await loadCatalog();
            await loadConfigView();
            await refreshMetaLine();
            appendMsg("bot", "Provider/Modelle aus Konfiguration neu geladen.");
          });

          // --- NEUE FUNKTIONEN: Provider & Modelle hinzufügen ---
          
          // --- NEUE FUNKTIONEN: Provider & Modelle verwalten ---
          
          async function renderLlmList() {
            const listEl = document.getElementById("llmList");
            if (!listEl) return;
            
            if (!catalog || !catalog.providers) {
              listEl.innerHTML = "Lade Katalog...";
              return;
            }

            let html = `<table style="width:100%; border-collapse:collapse; font-size:13px;">
              <thead>
                <tr style="background:var(--bg-2); text-align:left;">
                  <th style="padding:8px 10px; border-bottom:1px solid var(--line);">Provider</th>
                  <th style="padding:8px 10px; border-bottom:1px solid var(--line);">Basis URL / Token Alias</th>
                  <th style="padding:8px 10px; border-bottom:1px solid var(--line);">Modelle</th>
                  <th style="padding:8px 10px; border-bottom:1px solid var(--line);">Aktion</th>
                </tr>
              </thead>
              <tbody>`;

            catalog.providers.forEach(p => {
              const providerId = p.id;
              const models = p.models || [];
              const modelLinks = models.map(m => `
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:2px; padding:2px 4px; background:#f9fbff; border-radius:4px;">
                  <span>${escHtml(m)}</span>
                  <button class="secondary" style="font-size:10px; padding:1px 5px; color:#ef4444;" onclick="deleteLlmModel('${escHtml(providerId)}', '${escHtml(m)}')">🗑</button>
                </div>
              `).join("");

              html += `<tr style="border-bottom:1px solid var(--line); vertical-align:top;">
                <td style="padding:8px 10px;">
                  <strong>${escHtml(p.name)}</strong><br>
                  <code style="font-size:10px; color:var(--muted);">${escHtml(providerId)}</code>
                </td>
                <td style="padding:8px 10px; font-size:11px;">
                  ${p.base_url ? `URL: <code>${escHtml(p.base_url)}</code><br>` : ""}
                  ${p.api_key_alias ? `Alias: <code>${escHtml(p.api_key_alias)}</code><br>` : ""}
                  Status: ${p.api_key_set ? '<span style="color:#22c55e; font-weight:600;">✅ Token vorhanden</span>' : '<span style="color:#ef4444; font-weight:600;">❌ Kein Token</span>'}
                </td>
                <td style="padding:8px 10px;">${modelLinks || '<span class="muted">Keine Modelle</span>'}</td>
                <td style="padding:8px 10px;">
                  <button class="secondary" style="font-size:12px; padding:4px 8px; color:#ef4444;" onclick="deleteLlmProvider('${escHtml(providerId)}')">Provider löschen</button>
                </td>
              </tr>`;
            });

            html += `</tbody></table>`;
            listEl.innerHTML = html;
          }

          async function deleteLlmProvider(id) {
            if (!confirm(`Provider "${id}" und alle zugehörigen Modelle wirklich löschen?`)) return;
            try {
              const res = await fetch(`/api/config/provider/${encodeURIComponent(id)}`, { method: "DELETE" });
              const data = await res.json();
              if (res.ok) {
                appendMsg("bot", `Provider '${id}' gelöscht.`);
                await loadCatalog();
              } else {
                alert(`Fehler: ${data.detail || "unbekannt"}`);
              }
            } catch (e) { alert("Fehler: " + e); }
          }

          async function deleteLlmModel(providerId, modelName) {
            if (!confirm(`Modell "${modelName}" von Provider "${providerId}" wirklich entfernen?`)) return;
            try {
              const res = await fetch(`/api/config/provider/${encodeURIComponent(providerId)}/model/${encodeURIComponent(modelName)}`, { method: "DELETE" });
              const data = await res.json();
              if (res.ok) {
                appendMsg("bot", `Modell '${modelName}' entfernt.`);
                await loadCatalog();
              } else {
                alert(`Fehler: ${data.detail || "unbekannt"}`);
              }
            } catch (e) { alert("Fehler: " + e); }
          }

          // Expose to window for onclick handlers
          window.deleteLlmProvider = deleteLlmProvider;
          window.deleteLlmModel = deleteLlmModel;

          async function updateAddModelProviderDropdown() {
            const select = document.getElementById("addModelTargetProvider");
            if (!select) return;
            select.innerHTML = "";
            (catalog.providers || []).forEach(p => {
              const opt = document.createElement("option");
              opt.value = p.id;
              opt.textContent = `${p.name} (${p.id})`;
              select.appendChild(opt);
            });
          }

          document.getElementById("addProviderBtn").addEventListener("click", async () => {
            const id = document.getElementById("newProviderId").value.trim();
            const name = document.getElementById("newProviderName").value.trim();
            const url = document.getElementById("newProviderUrl").value.trim();
            const token = document.getElementById("newProviderToken").value.trim();
            const token_key = document.getElementById("newProviderTokenKey").value.trim();

            if (!id || !name) {
              alert("Bitte ID und Namen angeben.");
              return;
            }

            const res = await fetch("/api/config/provider/add", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id, name, base_url: url || null, token: token || null, token_key: token_key || null })
            });
            const data = await res.json();
            if (res.ok) {
              appendMsg("bot", `Provider '${name}' erfolgreich hinzugefügt.`);
              await loadCatalog();
              updateAddModelProviderDropdown();
            } else {
              alert(`Fehler: ${data.detail || "unbekannt"}`);
            }
          });

          document.getElementById("addModelBtn").addEventListener("click", async () => {
            const providerId = document.getElementById("addModelTargetProvider").value;
            const modelName = document.getElementById("newModelName").value.trim();

            if (!modelName) {
              alert("Bitte Modellnamen angeben.");
              return;
            }

            const res = await fetch("/api/config/model/add", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ provider_id: providerId, model_name: modelName })
            });
            const data = await res.json();
            if (res.ok) {
              appendMsg("bot", `Modell '${modelName}' zu '${providerId}' hinzugefügt.`);
              await loadCatalog();
            } else {
              alert(`Fehler: ${data.detail || "unbekannt"}`);
            }
          });

          // Initiale Befüllung des Modell-Ziel-Dropdowns nach dem Laden des Katalogs
          const oldLoadCatalog = loadCatalog;
          loadCatalog = async function() {
            await oldLoadCatalog();
            updateAddModelProviderDropdown();
            renderLlmList();
          };

          document.getElementById("applySecurity").addEventListener("click", async () => {
            const res = await fetch("/api/config/security", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                active_role: roleEl.value,
                execution_mode: execModeEl.value
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Sicherheits-Konfiguration gespeichert." : `Sicherheitsfehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyFilesystem").addEventListener("click", async () => {
            const res = await fetch("/api/config/filesystem", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                workspace: workspaceInputEl.value,
                full_access: fullAccessEl.value === "true",
                delete_to_trash: deleteToTrashEl.value === "true"
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Dateisystem-Konfiguration gespeichert." : `Dateisystem-Fehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyMcp").addEventListener("click", async () => {
            const res = await fetch("/api/config/mcp", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                timeout: Number(mcpTimeoutInputEl.value || 45),
                cache_ttl_sec: Number(mcpCacheTtlInputEl.value || 300),
                local_server_enabled: mcpLocalEnabledEl.value === "true"
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "MCP-Konfiguration gespeichert." : `MCP-Fehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyExecutionPlane").addEventListener("click", async () => {
            const res = await fetch("/api/config/execution_plane", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                show_console: execShowConsoleEl.value === "true"
              })
            });
            const data = await res.json().catch(() => ({}));
            appendMsg("bot", res.ok ? "Execution-Plane-Konfiguration gespeichert." : `Execution-Plane-Fehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
            await refreshExecutionPlaneStatus();
          });

          document.getElementById("reloadExecutionPlane").addEventListener("click", async () => {
            const res = await fetch("/api/execution/restart", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: "{}"
            });
            const data = await res.json().catch(() => ({}));
            appendMsg("bot", res.ok ? "Execution-Plane manuell neu geladen." : `Execution-Plane-Reload fehlgeschlagen: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await refreshExecutionPlaneStatus();
            await refreshMetaLine();
          });

          
          document.getElementById("applySelfImprove").addEventListener("click", async () => {
            const scan = Number(siScanIntervalEl.value || 300);
            const deep = Number(siDeepIntervalEl.value || 1800);
            const cooldown = Number(siCooldownEl.value || 900);
            const res = await fetch("/api/config/self_improve", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                enabled: siEnabledEl.value === "true",
                auto_execute: siAutoExecuteEl.value === "true",
                scan_interval_sec: Number.isFinite(scan) ? scan : 300,
                deep_check_interval_sec: Number.isFinite(deep) ? deep : 1800,
                cooldown_sec: Number.isFinite(cooldown) ? cooldown : 900
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Self-Improve-Konfiguration gespeichert." : `Self-Improve-Fehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
          });

          async function loadAudioVoices() {
            try {
              const res = await fetch("/api/audio/voices");
              const data = await res.json();
              if (res.ok && data.voices) {
                audioVoiceEl.innerHTML = "";
                data.voices.forEach(v => {
                  const opt = document.createElement("option");
                  opt.value = v.name;
                  opt.textContent = `${v.name} (${v.locale})`;
                  audioVoiceEl.appendChild(opt);
                });
              }
            } catch (err) {
              console.error("Failed to load audio voices:", err);
            }
          }

          async function loadAudioConfig() {
            try {
              const res = await fetch("/api/audio/config");
              const data = await res.json();
              if (res.ok) {
                audioEnabledEl.value = String(data.enabled);
                audioModeEl.value = String(data.mode || "reply_audio");
                if (data.voice) {
                  await loadAudioVoices();
                  if (Array.from(audioVoiceEl.options).some(o => o.value === data.voice)) {
                    audioVoiceEl.value = data.voice;
                  }
                }
              }
            } catch (err) {
              console.error("Failed to load audio config:", err);
            }
          }

          async function loadUiConfig() {
            try {
              const res = await fetch("/api/ui/config");
              const data = await res.json();
              if (res.ok) {
                quietModeEl.value = String(data.quiet_mode || false);
                showThinkingEl.value = String(data.show_thinking || false);
                showActionsEl.value = String(data.show_actions || false);
              }
            } catch (err) {
              console.error("Failed to load UI config:", err);
            }
          }

          async function loadReactRetryConfig() {
            try {
              const res = await fetch("/api/ui/config");
              const data = await res.json();
              if (res.ok) {
                const reactRetryEnabledEl = document.getElementById("reactRetryEnabled");
                const reactMaxRetriesEl = document.getElementById("reactMaxRetries");
                if (reactRetryEnabledEl) {
                  reactRetryEnabledEl.value = String(data.react_retry_enabled !== false);
                }
                if (reactMaxRetriesEl) {
                  reactMaxRetriesEl.value = String(data.react_max_retries || 3);
                }
              }
            } catch (err) {
              console.error("Failed to load React retry config:", err);
            }
          }

          async function loadReactLoopConfig() {
            try {
              const res = await fetch("/api/ui/config");
              const data = await res.json();
              if (res.ok) {
                const reactUseLoopEl = document.getElementById("reactUseLoop");
                const reactMaxIterationsEl = document.getElementById("reactMaxIterations");
                if (reactUseLoopEl) {
                  reactUseLoopEl.value = String(data.react_use_loop !== false);
                }
                if (reactMaxIterationsEl) {
                  reactMaxIterationsEl.value = String(data.react_max_iterations || 15);
                }
              }
            } catch (err) {
              console.error("Failed to load React loop config:", err);
            }
          }

          async function loadTimeoutsConfig() {
            try {
              const res = await fetch(noCacheUrl("/api/config"), { cache: "no-store" });
              const cfg = await res.json();
              
              if (timeoutMaxStepEl) timeoutMaxStepEl.value = String(cfg.cli_core?.max_step_timeout_sec || 600);
              if (timeoutLlmApiEl) timeoutLlmApiEl.value = String(cfg.llm?.llm_timeout_sec || 120);
              if (timeoutExecPlaneEl) timeoutExecPlaneEl.value = String(cfg.execution_plane?.request_timeout_sec || 1800);
              if (toolOutputCapCharsEl) toolOutputCapCharsEl.value = String(cfg.tools?.tool_output_cap_chars || 25000);
            } catch (err) {
              console.error("Failed to load timeouts config:", err);
            }
          }

          if (applyTimeoutsBtn) {
            applyTimeoutsBtn.addEventListener("click", async () => {
              const results = [];
              
              // 1. UI/LLM/Step Timeouts
              // LLM-Timeout + Max-Step-Timeout
              try {
                const resUi = await fetch("/api/ui/config", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    llm_timeout_sec: parseInt(timeoutLlmApiEl.value, 10),
                    max_step_timeout_sec: parseInt(timeoutMaxStepEl.value, 10)
                  })
                });
                if (resUi.ok) results.push("Step/LLM OK");
              } catch (e) { results.push("Step/LLM Fehler: " + e); }

              // Maximale Job-Laufzeit (universal, alle Quellen)
              try {
                const resEp = await fetch("/api/ui/config", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    request_timeout_sec: parseInt(timeoutExecPlaneEl.value, 10) || 1800
                  })
                });
                if (resEp.ok) results.push("Job-Laufzeit OK");
              } catch (e) { results.push("Job-Laufzeit Fehler: " + e); }

              // 3. Tool Output Cap
              if (toolOutputCapCharsEl) {
                try {
                  const resCap = await fetch("/api/config/tools", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      tool_output_cap_chars: parseInt(toolOutputCapCharsEl.value, 10) || 25000
                    })
                  });
                  if (resCap.ok) results.push("Auto-Save Cap OK");
                } catch (e) { results.push("Cap Fehler: " + e); }
              }

              appendMsg("bot", "Timeout-Einstellungen gespeichert: " + results.join(", "));
              await loadConfigView();
              await loadTimeoutsConfig();
            });
          }

          document.getElementById("refreshAudioVoices").addEventListener("click", async () => {
            await loadAudioVoices();
            appendMsg("bot", "Stimmen neu geladen.");
          });

          document.getElementById("applyAudio").addEventListener("click", async () => {
            const res = await fetch("/api/audio/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                enabled: audioEnabledEl.value === "true",
                voice: audioVoiceEl.value,
                mode: audioModeEl.value
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Audio-Konfiguration gespeichert." : `Audio-Fehler: ${data.detail || "unbekannt"}`);
            await loadToolLog();
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyUiOptions").addEventListener("click", async () => {
            const res = await fetch("/api/ui/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                quiet_mode: quietModeEl.value === "true",
                show_thinking: showThinkingEl.value === "true",
                show_actions: showActionsEl.value === "true"
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "UI-Optionen gespeichert." : `UI-Fehler: ${data.detail || "unbekannt"}`);
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyReactRetryOptions").addEventListener("click", async () => {
            const reactRetryEnabledEl = document.getElementById("reactRetryEnabled");
            const reactMaxRetriesEl = document.getElementById("reactMaxRetries");
            const res = await fetch("/api/ui/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                react_retry_enabled: reactRetryEnabledEl.value === "true",
                react_max_retries: parseInt(reactMaxRetriesEl.value, 10)
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Retry-Einstellungen gespeichert." : `Retry-Fehler: ${data.detail || "unbekannt"}`);
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("applyReactLoopOptions").addEventListener("click", async () => {
            const reactUseLoopEl = document.getElementById("reactUseLoop");
            const reactMaxIterationsEl = document.getElementById("reactMaxIterations");
            const res = await fetch("/api/ui/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                react_use_loop: reactUseLoopEl.value === "true",
                react_max_iterations: parseInt(reactMaxIterationsEl.value, 10)
              })
            });
            const data = await res.json();
            appendMsg("bot", res.ok ? "Loop-Einstellungen gespeichert." : `Loop-Fehler: ${data.detail || "unbekannt"}`);
            await loadConfigView();
            await refreshMetaLine();
          });

          document.getElementById("resetSessionUi").addEventListener("click", async () => {
            const ok = confirm("Aktuelle WebUI-Session wirklich neu starten?");
            if (!ok) return;
            const res = await fetch("/api/context/clear", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ scope: "conversation", session_key: "webui" })
            });
            const data = await res.json();
            if (res.ok) {
              appendMsg("bot", `Session neu gestartet: ${data.deleted_db || 0} Memory-Eintraege, ${data.cleared_sessions || 0} Session(s).`);
            } else {
              appendMsg("bot", `Session-Neustart fehlgeschlagen: ${data.detail || "unbekannt"}`);
            }
            await loadToolLog();
            await refreshMetaLine();
            switchTab("chat");
          });

          document.getElementById("testLlm").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/llm");
              const data = await res.json();
              appendTestOutput("LLM Live-Test", data, !res.ok || !data.ok);
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              appendTestOutput("LLM Live-Test", `Fehler: ${err.message || err}`, true);
            }
          });

          document.getElementById("testMessenger").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/messenger");
              const data = await res.json();
              appendTestOutput("Messenger-Test", data, !res.ok || !data.ok);
              await loadToolLog();
            } catch (err) {
              appendTestOutput("Messenger-Test", `Fehler: ${err.message || err}`, true);
            }
          });
          simulateRunEl.addEventListener("click", async () => {
            const message = String(simulateInputEl.value || "").trim();
            if (!message) {
              simulateOutputEl.style.display = "block";
              simulateOutputEl.textContent = "Bitte eine Anfrage eingeben.";
              return;
            }
            simulateOutputEl.style.display = "block";
            simulateOutputEl.textContent = "Simulation laeuft...";
            try {
              const res = await fetch("/api/simulate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message })
              });
              const data = await res.json();
              simulateOutputEl.textContent = normalizeDisplayText(JSON.stringify(data, null, 2));
            } catch (err) {
              simulateOutputEl.textContent = `Fehler: ${err.message || err}`;
            }
          });
          document.getElementById("testSelfImproveQuick").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/self_improve/quick");
              const data = await res.json();
              appendTestOutput("Self-Improve Klein", data, !res.ok || !data.ok);
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              appendTestOutput("Self-Improve Klein", `Fehler: ${err.message || err}`, true);
            }
          });
          document.getElementById("testSelfImproveDeep").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/self_improve/deep");
              const data = await res.json();
              appendTestOutput("Self-Improve Ausfuehrlich", data, !res.ok || !data.ok);
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              appendTestOutput("Self-Improve Ausfuehrlich", `Fehler: ${err.message || err}`, true);
            }
          });
          document.getElementById("testSelfImproveDiagnose").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/self_improve/diagnose", { method: "POST" });
              const data = await res.json();
              appendTestOutput("Self-Improve Diagnose", data, !res.ok || !data.ok);
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              appendTestOutput("Self-Improve Diagnose", `Fehler: ${err.message || err}`, true);
            }
          });
          document.getElementById("testDoctor").addEventListener("click", async () => {
            try {
              const res = await fetch("/api/tests/doctor");
              const data = await res.json();
              appendTestOutput("System-Doctor", data, !res.ok || !data.ok);
              await loadToolLog();
              await refreshMetaLine();
            } catch (err) {
              appendTestOutput("System-Doctor", `Fehler: ${err.message || err}`, true);
            }
          });
          document.getElementById("clearTestOutput").addEventListener("click", () => {
            testOutputEl.innerHTML = "";
          });

          document.getElementById("refreshConfig").addEventListener("click", async () => {
            await loadCatalog();
            await loadConfigView();
            appendMsg("bot", "Konfigurationsübersicht aktualisiert.");
          });
          document.getElementById("refreshCronJobs").addEventListener("click", async () => {
            await loadCronJobs();
          });
          refreshSkillsEl.addEventListener("click", async () => {
            await fetch("/api/skills/reload", { method: "POST" });
            await loadSkills();
            await loadConfigView();
          });
          cronActiveOnlyEl.addEventListener("change", async () => {
            await loadCronJobs();
          });
          document.getElementById("refreshAuditLog").addEventListener("click", async () => {
            await loadAuditLog();
          });
          document.getElementById("clearAuditLog").addEventListener("click", async () => {
            const ok = confirm("Audit-Log wirklich loeschen?");
            if (!ok) return;
            const res = await fetch("/api/logs/audit", { method: "DELETE" });
            const data = await res.json();
            if (res.ok) {
              appendMsg("bot", `Audit-Log geloescht: ${normalizeDisplayText(String(data.path || ""))}`);
            } else {
              appendMsg("bot", `Fehler beim Loeschen des Audit-Logs: ${normalizeDisplayText(String(data.detail || "unbekannt"))}`);
            }
            await loadAuditLog();
            await loadToolLog();
          });

          // Fehler-Log laden und löschen
          async function loadErrorLog() {
            const el = document.getElementById("errorLogList");
            const meta = document.getElementById("errorLogMeta");
            if (!el) return;
            el.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
            meta.style.color = "";
            try {
              const r = await fetch("/api/logs/errors?limit=200");
              const d = await r.json();
              const entries = d.entries || [];
              if (entries.length === 0) {
                el.innerHTML = '<p style="color:var(--muted);padding:6px 0;">Keine Fehler-Einträge.</p>';
                meta.textContent = "Log ist leer.";
                return;
              }
              meta.textContent = `${entries.length} Einträge`;
              el.innerHTML = `<table style="width:100%;border-collapse:collapse;">
          <thead><tr style="background:var(--bg-2);text-align:left;">
            <th style="padding:5px 8px;border-bottom:1px solid var(--line);font-size:12px;">Zeit</th>
            <th style="padding:5px 8px;border-bottom:1px solid var(--line);font-size:12px;">Typ</th>
            <th style="padding:5px 8px;border-bottom:1px solid var(--line);font-size:12px;">Meldung</th>
          </tr></thead><tbody>` +
                entries.map(e => `<tr style="border-bottom:1px solid var(--line);">
            <td style="padding:5px 8px;font-size:11px;color:var(--muted);white-space:nowrap;">${escHtml(fmtTs(e.ts))}</td>
            <td style="padding:5px 8px;font-size:11px;white-space:nowrap;"><code style="color:#f59e0b;">${escHtml(e.kind || "")}</code></td>
            <td style="padding:5px 8px;font-size:11px;color:var(--muted);max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml((e.message || "").slice(0, 250))}</td>
          </tr>`).join("") + "</tbody></table>";
            } catch (e) { el.innerHTML = `<span style="color:#ef4444">Fehler: ${e}</span>`; }
          }

          document.getElementById("refreshErrorLog").addEventListener("click", loadErrorLog);
          document.getElementById("clearErrorLog").addEventListener("click", async () => {
            if (!confirm("Fehler-Log (errors.log) wirklich löschen?")) return;
            try {
              const r = await fetch("/api/logs/errors", { method: "DELETE" });
              const d = await r.json();
              const meta = document.getElementById("errorLogMeta");
              if (d.ok) {
                meta.textContent = `✔ Fehler-Log gelöscht (${d.deleted_bytes} Bytes)`;
                meta.style.color = "#22c55e";
                document.getElementById("errorLogList").innerHTML = '<p style="color:var(--muted);padding:6px 0;">Log geleert.</p>';
              } else {
                meta.textContent = "Fehler beim Löschen";
                meta.style.color = "#ef4444";
              }
            } catch (e) { document.getElementById("errorLogMeta").textContent = "Fehler: " + e; }
          });

          document.getElementById("qaListFiles").addEventListener("click", async () => { await postStreamMessage("Liste alle Dateien in data\\workspace rekursiv"); switchTab("chat"); });
          document.getElementById("qaListDirs").addEventListener("click", async () => { await postStreamMessage("Liste Ordner in data\\workspace"); switchTab("chat"); });
          document.getElementById("qaMemoryShow").addEventListener("click", async () => {
            await postStreamMessage("/gedaechtnis anzeigen");
            switchTab("chat");
          });
          document.getElementById("qaMemoryDelete").addEventListener("click", async () => {
            await postStreamMessage("/gedaechtnis loeschen");
            switchTab("chat");
          });
          document.getElementById("qaClearContext").addEventListener("click", async () => {
            await postStreamMessage("/kontext loeschen");
            switchTab("chat");
          });
          document.getElementById("qaCronJobs").addEventListener("click", async () => {
            await postStreamMessage("/cron jobs");
            switchTab("chat");
          });

          // ========== Queue-Management ==========
          let queueRefreshInterval = null;

          async function refreshQueueStats() {
            try {
              const res = await fetch("/api/queue/stats");
              const data = await res.json();

              if (!data.ok) {
                document.getElementById("queueSize").textContent = "?";
                document.getElementById("activeCount").textContent = "?";
                document.getElementById("workerStatus").textContent = "Fehler";
                return;
              }

              document.getElementById("queueSize").textContent = data.queue_size || 0;
              document.getElementById("activeCount").textContent = data.active_requests || 0;

              const workerStatus = data.worker_alive ? "🟢 Aktiv" : "🔴 Gestoppt";
              document.getElementById("workerStatus").textContent = workerStatus;

              // Aktive Requests
              const listEl = document.getElementById("activeRequestsList");
              listEl.innerHTML = "";

              if (!data.active_details || data.active_details.length === 0) {
                listEl.innerHTML = '<div style="color:var(--muted);padding:12px;text-align:center;">Keine aktiven Jobs</div>';
              } else {
                console.log("[Queue] Active jobs:", data.active_details);
                data.active_details.forEach((job, idx) => {
                  console.log(`[Queue] Job ${idx}:`, job);
                  const statusColor = job.status === "cancelling" ? "#ef4444" : "#2563eb";
                  const statusText = job.status === "cancelling" ? "Wird abgebrochen..." : `${job.runtime}s`;

                  const div = document.createElement("div");
                  div.style.cssText = "background:linear-gradient(135deg,#f0f9ff 0%,#e0f2fe 100%);border-left:3px solid " + statusColor + ";border-radius:8px;padding:12px;margin-bottom:8px;";
                  div.innerHTML = `
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="flex:1;">
                  <strong style="color:#1e40af;">Job ${idx + 1}</strong>
                  <div style="color:#64748b;font-size:12px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                    ${job.message || ""}
                  </div>
                  <div style="color:#94a3b8;font-size:11px;margin-top:2px;">
                    ${job.source || "unknown"} • ${job.dialog_key || ""} • trace_id: ${job.trace_id || "missing"}
                  </div>
                </div>
                <div style="display:flex;align-items:center;gap:8px;margin-left:12px;">
                  <div style="text-align:right;">
                    <div style="font-size:14px;font-weight:600;color:${statusColor};">
                      ${statusText}
                    </div>
                  </div>
                  <button 
                    onclick="cancelRequest('${job.trace_id}')"
                    style="background:#dc2626;color:white;border:none;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px;font-weight:600;${job.status === 'cancelling' ? 'opacity:0.5;cursor:not-allowed;' : ''}"
                    ${job.status === 'cancelling' ? 'disabled' : ''}
                    onmouseover="if(!this.disabled) this.style.background='#b91c1c'"
                    onmouseout="if(!this.disabled) this.style.background='#dc2626'"
                  >
                    ✕ Abbrechen
                  </button>
                </div>
              </div>
            `;
                  listEl.appendChild(div);
                });
              }

              // Wartende Requests (leer, da keine echte Queue mehr)
              const pendingEl = document.getElementById("pendingRequestsList");
              if (pendingEl) {
                pendingEl.innerHTML = '<div style="color:var(--muted);padding:12px;text-align:center;">Keine wartenden Requests</div>';
              }

            } catch (e) {
              console.error("Queue-Stats Fehler:", e);
            }
          }

          async function cancelRequest(requestId) {
            if (!confirm("Request wirklich abbrechen?")) {
              return;
            }

            try {
              const res = await fetch(`/api/queue/cancel/${requestId}`, { method: "POST" });
              const data = await res.json();

              if (data.ok) {
                if (data.cancelled) {
                  appendMsg("system", `Request ${requestId.substring(0, 8)}... wurde abgebrochen.`);
                } else {
                  appendMsg("system", `Request konnte nicht abgebrochen werden (bereits aktiv oder nicht gefunden).`);
                }
                refreshQueueStats();
              } else {
                appendMsg("system", "Fehler beim Abbrechen: " + (data.error || "Unbekannt"));
              }
            } catch (e) {
              appendMsg("system", "Fehler beim Abbrechen: " + e);
            }
          }

          async function clearQueue() {
            if (!confirm("Alle aktiven Jobs wirklich abbrechen?")) {
              return;
            }

            try {
              const res = await fetch("/api/queue/clear", { method: "POST" });
              const data = await res.json();

              if (data.ok) {
                alert(`${data.cleared || 0} Job(s) werden abgebrochen`);
                refreshQueueStats();
              } else {
                alert("Fehler: " + (data.error || "Unbekannt"));
              }
            } catch (e) {
              alert("Fehler beim Abbrechen: " + e);
            }
          }

          document.getElementById("refreshQueue").addEventListener("click", refreshQueueStats);
          document.getElementById("clearQueue").addEventListener("click", clearQueue);

          document.getElementById("queueAutoRefresh").addEventListener("change", (e) => {
            const interval = parseInt(e.target.value);

            if (queueRefreshInterval) {
              clearInterval(queueRefreshInterval);
              queueRefreshInterval = null;
            }

            if (interval > 0) {
              queueRefreshInterval = setInterval(refreshQueueStats, interval);
            }
          });

          // Auto-Refresh initial starten (2s ist default selected)
          const initialInterval = parseInt(document.getElementById("queueAutoRefresh").value);
          if (initialInterval > 0) {
            queueRefreshInterval = setInterval(refreshQueueStats, initialInterval);
          }

          const originalSwitchTab = switchTab;
          switchTab = function (tabName) {
            originalSwitchTab(tabName);
            if (tabName === "queue") {
              refreshQueueStats();
            }
          };

          document.getElementById("qaConfigRefresh").addEventListener("click", async () => {
            await loadCatalog();
            await loadConfigView();
            appendMsg("bot", "Konfigurationsübersicht aktualisiert.");
            switchTab("chat");
          });
          document.getElementById("refreshSecretsBtn").addEventListener("click", async () => {
            await loadSecrets();
            appendMsg("bot", "Secret-Alias-Liste aktualisiert.");
          });
          document.getElementById("saveSecretBtn").addEventListener("click", async () => {
            await saveSecretWithConfirm(secretAliasEl.value, secretValueEl.value);
          });
          document.getElementById("deleteSecretBtn").addEventListener("click", async () => {
            await deleteSecretWithConfirm(secretAliasEl.value);
          });

          (async function init() {
            applyFieldHints();
            await loadCatalog();
            await loadToolLog();
            await loadAuditLog();
            await loadConfigView();
            await loadTimeoutsConfig();
            await loadCronJobs();
            await loadSkills();
            await loadSecrets();
            await loadAudioVoices();
            await loadAudioConfig();
            await loadUiConfig();
            await loadReactRetryConfig();
            await loadReactLoopConfig();
            await refreshMetaLine();
            await loadNotifications();
            setInterval(renderMetaLine, 1000);
            setInterval(refreshMetaLine, 6000);
            setInterval(loadNotifications, 5000);
            await loadMemory();
          })();

          // Memory Panel
          async function loadMemory() {
            const kind = document.getElementById("memKindFilter").value;
            const url = "/api/memory" + (kind ? "?kind=" + encodeURIComponent(kind) : "");
            try {
              const r = await fetch(url);
              const d = await r.json();
              const tbody = document.getElementById("memTableBody");
              document.getElementById("memCount").textContent = d.ok ? d.count + " Eintr\u00e4ge" : "Fehler";
              tbody.innerHTML = "";
              (d.items || []).forEach(item => {
                const content = typeof item.content === "object" ? JSON.stringify(item.content) : String(item.content || "");
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid var(--line)";
                tr.innerHTML = `<td style="padding:6px 10px;">${escHtml(item.kind || "")}</td>
            <td style="padding:6px 10px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(item.key || "")}">${escHtml(item.key || "")}</td>
            <td style="padding:6px 10px;">${typeof item.confidence === "number" ? item.confidence.toFixed(2) : ""}</td>
            <td style="padding:6px 10px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(content)}">${escHtml(content.slice(0, 80))}${content.length > 80 ? "…" : ""}</td>
            <td style="padding:6px 10px;white-space:nowrap;">${escHtml(item.updated_at ? item.updated_at.slice(0, 16) : "")}</td>
            <td style="padding:6px 10px;"><button class="mem-del-btn" data-kind="${escHtml(item.kind || "")}" data-key="${escHtml(item.key || "")}" style="padding:3px 8px;border-radius:6px;border:1px solid var(--bad);background:#fff0ee;color:var(--bad);cursor:pointer;font-size:12px;">L\u00f6schen</button></td>`;
                tbody.appendChild(tr);
              });
              document.querySelectorAll(".mem-del-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                  const k = btn.dataset.kind, key = btn.dataset.key;
                  if (!confirm("Eintrag l\u00f6schen: " + k + ":" + key.slice(0, 60) + "?")) return;
                  const statusEl = document.getElementById("memStatus");
                  btn.disabled = true;
                  btn.textContent = "…";
                  try {
                    const r = await fetch("/api/memory/delete_entry", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ kind: k, key: key })
                    });
                    const d = await r.json();
                    if (d.ok) {
                      statusEl.style.color = "var(--good,#22c55e)";
                      statusEl.textContent = "\u2714 Gel\u00f6scht: " + k + ":" + key.slice(0, 40);
                    } else {
                      statusEl.style.color = "var(--bad,#ef4444)";
                      statusEl.textContent = "\u2716 Fehler: " + (d.error || "unbekannt");
                    }
                  } catch (e) {
                    statusEl.style.color = "var(--bad,#ef4444)";
                    statusEl.textContent = "\u2716 Netzwerkfehler";
                  }
                  await loadMemory();
                });
              });
            } catch (e) {
              document.getElementById("memCount").textContent = "Ladefehler";
            }
          }
          async function memDeleteAll() {
            const kind = document.getElementById("memKindFilter").value;
            const label = kind ? "alle '" + kind + "'-Eintr\u00e4ge" : "ALLE Ged\u00e4chtnis-Eintr\u00e4ge";
            if (!confirm(label + " wirklich l\u00f6schen?")) return;
            const statusEl = document.getElementById("memStatus");
            statusEl.style.color = "var(--muted)";
            statusEl.textContent = "L\u00f6sche…";
            try {
              const url = "/api/memory/delete_all" + (kind ? "?kind=" + encodeURIComponent(kind) : "");
              const r = await fetch(url, { method: "DELETE" });
              const d = await r.json();
              if (d.ok) {
                statusEl.style.color = "var(--good,#22c55e)";
                statusEl.textContent = "\u2714 " + (d.deleted || 0) + " Eintr\u00e4ge gel\u00f6scht";
              } else {
                statusEl.style.color = "var(--bad,#ef4444)";
                statusEl.textContent = "\u2716 Fehler: " + (d.error || "unbekannt");
              }
            } catch (e) {
              statusEl.style.color = "var(--bad,#ef4444)";
              statusEl.textContent = "\u2716 Netzwerkfehler";
            }
            await loadMemory();
          }
          function escHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
          function fmtTs(iso) {
            if (!iso) return "";
            try {
              const d = new Date(iso);
              return d.toLocaleString("de-DE", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
            } catch { return String(iso).slice(0, 19).replace("T", " "); }
          }
          // Langzeit-Fakten (discovered_facts)
          async function loadFacts() {
            const tbody = document.getElementById("factsTableBody");
            const emptyEl = document.getElementById("factsEmpty");
            const countEl = document.getElementById("factsCount");
            try {
              const r = await fetch("/api/facts");
              const d = await r.json();
              tbody.innerHTML = "";
              if (!d.ok || !d.items || d.items.length === 0) {
                emptyEl.style.display = "";
                countEl.textContent = "0 Fakten";
                return;
              }
              emptyEl.style.display = "none";
              countEl.textContent = d.count + " Fakt" + (d.count !== 1 ? "en" : "");
              d.items.forEach(item => {
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid var(--line)";
                const ts = item.timestamp ? item.timestamp.slice(0, 16).replace("T", " ") : "";
                tr.innerHTML = `<td style="padding:7px 10px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(item.key)}">${escHtml(item.key)}</td>
                  <td style="padding:7px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(item.value)}">${escHtml(item.value)}</td>
                  <td style="padding:7px 10px;white-space:nowrap;color:var(--muted);font-size:12px;">${escHtml(ts)}</td>
                  <td style="padding:7px 10px;text-align:center;"><button class="fact-del-btn" data-key="${escHtml(item.key)}" style="padding:3px 8px;border-radius:6px;border:1px solid var(--bad,#ef4444);background:#fff0ee;color:var(--bad,#ef4444);cursor:pointer;font-size:12px;">✕</button></td>`;
                tbody.appendChild(tr);
              });
              document.querySelectorAll(".fact-del-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                  const key = btn.dataset.key;
                  if (!confirm("Fakt löschen: " + key + "?")) return;
                  btn.disabled = true; btn.textContent = "…";
                  try {
                    const r = await fetch("/api/facts/" + encodeURIComponent(key), { method: "DELETE" });
                    const d = await r.json();
                    document.getElementById("factsStatus").textContent = d.ok ? "✔ " + d.message : "✖ " + (d.message || "Fehler");
                    document.getElementById("factsStatus").style.color = d.ok ? "var(--good,#22c55e)" : "var(--bad,#ef4444)";
                  } catch(e) { document.getElementById("factsStatus").textContent = "✖ Netzwerkfehler"; }
                  await loadFacts();
                });
              });
            } catch(e) {
              countEl.textContent = "Ladefehler: " + (e.message || String(e));
              console.error("loadFacts error:", e);
            }
          }
          document.getElementById("refreshFacts").addEventListener("click", loadFacts);

          document.getElementById("refreshMemory").addEventListener("click", loadMemory);
          document.getElementById("memDeleteAllBtn").addEventListener("click", memDeleteAll);
          document.getElementById("memKindFilter").addEventListener("change", loadMemory);
          document.getElementById("memTraceSearch").addEventListener("click", async () => {
            const tid = document.getElementById("memTraceInput").value.trim();
            const el = document.getElementById("memTraceResult");
            if (!tid) return;
            el.style.display = "block";
            el.textContent = "Lade " + tid + "…";
            try {
              const r = await fetch("/api/memory/trace/" + encodeURIComponent(tid) + "?t=" + Date.now());
              const d = await r.json();
              el.textContent = JSON.stringify(d, null, 2);
            } catch (e) { el.textContent = "Fehler: " + e; }
          });

          // ─── Self-Improve ────────────────────────────────────────────────────────
          const SI_RISK_COLOR = { low: "#22c55e", medium: "#f59e0b", high: "#ef4444" };
          const SI_STATUS_LABEL = {
            proposed: "Vorschlag", applied: "Angewendet", rejected: "Abgelehnt",
            restored: "Wiederhergestellt", failed: "Fehlgeschlagen"
          };

          function siRiskBadge(risk) {
            const c = SI_RISK_COLOR[risk] || "#888";
            return `<span style="background:${c}22;color:${c};border:1px solid ${c};border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700;">${(risk || "?").toUpperCase()}</span>`;
          }

          function siStatusBadge(status) {
            const colors = { proposed: "#60a5fa", applied: "#22c55e", rejected: "#6b7280", restored: "#a78bfa", failed: "#ef4444" };
            const c = colors[status] || "#888";
            return `<span style="color:${c};font-size:12px;font-weight:700;">${SI_STATUS_LABEL[status] || status}</span>`;
          }

          async function siLoadPatches() {
            const elP = document.getElementById("siPatchListProposed");
            const elA = document.getElementById("siPatchListApplied");
            const elR = document.getElementById("siPatchListRejected");
            [elP, elA, elR].forEach(el => el.innerHTML = '<span style="color:var(--muted);font-size:13px;">Lade…</span>');
            try {
              const r = await fetch("/api/selfimprove/patches");
              const d = await r.json();
              const patches = d.patches || [];

              const proposed = patches.filter(p => p.status === "proposed");
              const applied = patches.filter(p => ["applied", "failed", "restored"].includes(p.status));
              const rejected = patches.filter(p => p.status === "rejected");

              document.getElementById("siCountProposed").textContent = proposed.length ? `(${proposed.length})` : "";
              document.getElementById("siCountApplied").textContent = applied.length ? `(${applied.length})` : "";
              document.getElementById("siCountRejected").textContent = rejected.length ? `(${rejected.length})` : "";

              const renderCard = (p) => `
          <div style="background:var(--bg-2);border-radius:10px;padding:14px 16px;margin-bottom:10px;border:1px solid var(--line);">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
              ${siStatusBadge(p.status)} ${siRiskBadge(p.risk)}
              <strong style="flex:1;min-width:120px;">${escHtml(p.title || "Patch")}</strong>
              <span style="font-size:11px;color:var(--muted);">${fmtTs(p.created_at)}</span>
            </div>
            <div style="font-size:13px;color:var(--muted);margin-bottom:8px;">${escHtml(p.root_cause || "")}</div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">
              ${(p.changes || []).length} Änderung(en): ${(p.changes || []).map(c => `<code>${escHtml(c.file || "?")}</code>`).join(", ")}
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button class="secondary" style="font-size:12px;padding:4px 10px;" onclick="siShowDetail('${escHtml(p.id)}')">Details</button>
              ${p.status === "proposed" ? `
                <button class="primary" style="font-size:12px;padding:4px 10px;background:#22c55e;" onclick="siApplyPatch('${escHtml(p.id)}')">✔ Anwenden</button>
                <button class="secondary" style="font-size:12px;padding:4px 10px;color:#ef4444;" onclick="siRejectPatch('${escHtml(p.id)}')">✗ Ablehnen</button>
              ` : ""}
              ${(p.status === "applied" || p.status === "failed") ? `
                <button class="secondary" style="font-size:12px;padding:4px 10px;color:#a78bfa;" onclick="siRestorePatch('${escHtml(p.id)}')">↩ Wiederherstellen</button>
              ` : ""}
            </div>
          </div>`;

              const empty = '<p style="color:var(--muted);font-size:13px;padding:6px 0;">Keine Einträge.</p>';
              elP.innerHTML = proposed.length ? proposed.map(renderCard).join("") : empty;
              elA.innerHTML = applied.length ? applied.map(renderCard).join("") : empty;
              elR.innerHTML = rejected.length ? rejected.map(renderCard).join("") : empty;
            } catch (e) {
              [elP, elA, elR].forEach(el => el.innerHTML = `<span style="color:#ef4444">Fehler: ${e}</span>`);
            }
          }

          async function siLoadReports() {
            const el = document.getElementById("siReportList");
            el.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
            try {
              const r = await fetch("/api/selfimprove/reports?limit=15");
              const d = await r.json();
              if (!d.reports || d.reports.length === 0) {
                el.innerHTML = '<p style="color:var(--muted);font-size:13px;">Keine Reports vorhanden.</p>';
                return;
              }
              el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:var(--bg-2);text-align:left;">
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Typ</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Zeitpunkt</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Signale</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">LLM</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Top-Fehler</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);"></th>
          </tr></thead><tbody>` +
                d.reports.map(rep => `<tr style="border-bottom:1px solid var(--line);">
            <td style="padding:6px 10px;">${escHtml(rep.type || "?")}</td>
            <td style="padding:6px 10px;white-space:nowrap;">${fmtTs(rep.generated_at)}</td>
            <td style="padding:6px 10px;text-align:center;">${rep.signal_count ?? "-"}</td>
            <td style="padding:6px 10px;">${rep.llm_ok === true ? "✅" : rep.llm_ok === false ? "❌" : "—"}</td>
            <td style="padding:6px 10px;color:var(--muted);font-size:12px;">${(rep.top_signals || []).map(s => escHtml(s.key || "")).join(", ") || "—"}</td>
            <td style="padding:4px 6px;">
              <button class="secondary" style="font-size:11px;padding:3px 8px;color:#ef4444;" onclick="siDeleteReport('${escHtml(rep.file)}')">🗑</button>
            </td>
          </tr>`).join("") + "</tbody></table>";
            } catch (e) { el.innerHTML = `<span style="color:#ef4444">Fehler: ${e}</span>`; }
          }

          async function siDeleteReport(filename) {
            if (!confirm(`Report "${filename}" wirklich löschen?`)) return;
            try {
              const r = await fetch(`/api/selfimprove/reports/${encodeURIComponent(filename)}`, { method: "DELETE" });
              const d = await r.json();
              if (d.ok) { siLoadReports(); }
              else { alert("Fehler: " + (d.message || "Unbekannt")); }
            } catch (e) { alert("Fehler: " + e); }
          }

          async function siDeleteAllReports() {
            if (!confirm("Alle Scan-Reports wirklich löschen?")) return;
            try {
              const r = await fetch("/api/selfimprove/reports", { method: "DELETE" });
              const d = await r.json();
              siLoadReports();
              document.getElementById("siStatus").textContent = `${d.deleted} Report(s) gelöscht.`;
              setTimeout(() => document.getElementById("siStatus").textContent = "", 3000);
            } catch (e) { alert("Fehler: " + e); }
          }

          async function siShowDetail(patchId) {
            const modal = document.getElementById("siModal");
            const content = document.getElementById("siModalContent");
            content.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
            modal.style.display = "block";
            try {
              const r = await fetch(`/api/selfimprove/patches/${encodeURIComponent(patchId)}`);
              const d = await r.json();
              const p = d.patch || {};
              content.innerHTML = `
          <h3 style="margin-top:0;">${escHtml(p.title || "Patch")}</h3>
          <div style="display:flex;gap:8px;margin-bottom:10px;">${siStatusBadge(p.status)} ${siRiskBadge(p.risk)}</div>
          <p><strong>Ursache:</strong> ${escHtml(p.root_cause || "—")}</p>
          <p><strong>Erstellt:</strong> ${fmtTs(p.created_at)}</p>
          ${p.applied_at ? `<p><strong>Angewendet:</strong> ${fmtTs(p.applied_at)}</p>` : ""}
          ${p.has_backup ? `<p style="color:#22c55e;">✔ Fallback-Backup vorhanden: ${(p.backup_files || []).join(", ")}</p>` : ""}
          <hr style="border-color:var(--line);margin:12px 0;">
          <strong>Änderungen (${(p.changes || []).length}):</strong>
          ${(p.changes || []).map((c, i) => `
            <div style="background:var(--bg-2);border-radius:8px;padding:10px 12px;margin-top:8px;border:1px solid var(--line);">
              <div style="margin-bottom:4px;font-size:12px;color:var(--muted);">#${i + 1} · <code>${escHtml(c.file || "?")}</code> · <em>${escHtml(c.type || "?")}</em></div>
              ${c.description ? `<div style="font-size:13px;margin-bottom:6px;">${escHtml(c.description)}</div>` : ""}
              ${c.search ? `<pre style="background:#1a1a2e;color:#a5f3fc;border-radius:6px;padding:8px;font-size:11px;overflow-x:auto;margin:4px 0;">- ${escHtml(c.search)}</pre>` : ""}
              ${c.replace ? `<pre style="background:#1a2e1a;color:#86efac;border-radius:6px;padding:8px;font-size:11px;overflow-x:auto;margin:4px 0;">+ ${escHtml(c.replace)}</pre>` : ""}
              ${c.content ? `<pre style="background:var(--bg-2);border-radius:6px;padding:8px;font-size:11px;overflow-x:auto;margin:4px 0;">${escHtml(c.content.slice(0, 400))}</pre>` : ""}
            </div>`).join("")}
          ${p.apply_results ? `<hr style="border-color:var(--line);margin:12px 0;"><strong>Ergebnis:</strong>
            ${(p.apply_results || []).map(r => `<div style="font-size:12px;color:${r.ok ? "#22c55e" : "#ef4444"};">
              ${r.ok ? "✔" : "✗"} ${escHtml(r.file || "")} – ${escHtml(r.message || "")}</div>`).join("")}` : ""}
          <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap;">
            ${p.status === "proposed" ? `
              <button class="primary" style="background:#22c55e;" onclick="siApplyPatch('${escHtml(p.id)}');document.getElementById('siModal').style.display='none'">✔ Anwenden</button>
              <button class="secondary" style="color:#ef4444;" onclick="siRejectPatch('${escHtml(p.id)}');document.getElementById('siModal').style.display='none'">✗ Ablehnen</button>` : ""}
            ${(p.status === "applied" || p.status === "failed") ? `
              <button class="secondary" style="color:#a78bfa;" onclick="siRestorePatch('${escHtml(p.id)}');document.getElementById('siModal').style.display='none'">↩ Wiederherstellen</button>` : ""}
            <button class="secondary" onclick="document.getElementById('siModal').style.display='none'">Schließen</button>
          </div>`;
            } catch (e) { content.innerHTML = `<span style="color:#ef4444">Fehler: ${e}</span>`; }
          }

          async function siApplyPatch(id) {
            if (!confirm(`Patch ${id} wirklich anwenden? Backup wird in data/patch_fallback/ gespeichert.`)) return;
            const st = document.getElementById("siStatus");
            st.textContent = "Wende Patch an…";
            try {
              const r = await fetch(`/api/selfimprove/patches/${encodeURIComponent(id)}/apply`, { method: "POST" });
              const d = await r.json();
              st.textContent = d.ok ? `✔ ${d.message}` : `✗ ${d.message}`;
              st.style.color = d.ok ? "#22c55e" : "#ef4444";
              siLoadPatches();
            } catch (e) { st.textContent = "Fehler: " + e; st.style.color = "#ef4444"; }
          }

          async function siRejectPatch(id) {
            const st = document.getElementById("siStatus");
            try {
              const r = await fetch(`/api/selfimprove/patches/${encodeURIComponent(id)}/reject`, { method: "POST" });
              const d = await r.json();
              st.textContent = d.ok ? "Patch abgelehnt" : `✗ ${d.message}`;
              siLoadPatches();
            } catch (e) { st.textContent = "Fehler: " + e; }
          }

          async function siRestorePatch(id) {
            if (!confirm(`Fallback für Patch ${id} wiederherstellen? Aktuelle Dateien werden überschrieben.`)) return;
            const st = document.getElementById("siStatus");
            st.textContent = "Stelle wieder her…";
            try {
              const r = await fetch(`/api/selfimprove/patches/${encodeURIComponent(id)}/restore`, { method: "POST" });
              const d = await r.json();
              st.textContent = d.ok ? `✔ ${d.message}` : `✗ ${d.message}`;
              st.style.color = d.ok ? "#22c55e" : "#ef4444";
              siLoadPatches();
            } catch (e) { st.textContent = "Fehler: " + e; st.style.color = "#ef4444"; }
          }

          document.getElementById("siAnalyzeBtn").addEventListener("click", async () => {
            const st = document.getElementById("siStatus");
            st.textContent = "Analysiere Fehlersignale…"; st.style.color = "var(--muted)";
            try {
              const r = await fetch("/api/selfimprove/analyze", { method: "POST" });
              const d = await r.json();
              st.textContent = d.ok ? `✔ ${d.message}` : `ℹ ${d.message}`;
              st.style.color = d.ok ? "#22c55e" : "var(--muted)";
              siLoadPatches();
            } catch (e) { st.textContent = "Fehler: " + e; st.style.color = "#ef4444"; }
          });

          document.getElementById("siRefreshBtn").addEventListener("click", () => {
            siLoadPatches(); siLoadReports();
          });

          document.getElementById("siDeleteAllReportsBtn").addEventListener("click", siDeleteAllReports);

          // ── MCP Tools Tab ───────────────────────────────────────────────────
          let _mcpToolsData = [];
          let _toolTreeData = null;

          function _renderToolTreeNode(node, depth = 0) {
            if (!node || typeof node !== "object") return "";
            const kind = String(node.kind || "").toLowerCase();
            const pad = Math.max(0, Number(depth) || 0) * 14;
            if (kind === "tool") {
              const source = String(node.source || "").toLowerCase();
              const sourceColor = source === "mcp" ? "#0f6a8f" : (source === "skill" ? "#b45309" : "var(--muted)");
              const meta = [];
              if (node.server) meta.push(`server=${escHtml(String(node.server))}`);
              if (node.created_by_role) meta.push(`role=${escHtml(String(node.created_by_role))}`);
              if (node.skill_id) meta.push(`skill=${escHtml(String(node.skill_id))}`);
              if (Object.prototype.hasOwnProperty.call(node, "enabled")) meta.push(`enabled=${node.enabled ? "true" : "false"}`);
              if (node.category_path) meta.push(`category=${escHtml(String(node.category_path))}`);
              return `<div style="margin-left:${pad}px;padding:4px 0;border-bottom:1px dashed var(--line);">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <code style="font-size:12px;">${escHtml(String(node.name || "?"))}</code>
            <span style="font-size:11px;color:${sourceColor};font-weight:600;">${escHtml(source || "tool")}</span>
          </div>
          <div style="font-size:12px;color:var(--muted);">${escHtml(String(node.description || "—"))}</div>
          ${meta.length ? `<div style="font-size:11px;color:var(--muted);">${meta.join(" · ")}</div>` : ""}
        </div>`;
            }
            const title = escHtml(String(node.name || "group"));
            const children = Array.isArray(node.children) ? node.children : [];
            const openAttr = depth <= 1 ? "open" : "";
            return `<details ${openAttr} style="margin-left:${pad}px;">
        <summary style="cursor:pointer;font-weight:600;">${title} <span style="color:var(--muted);font-weight:400;">(${children.length})</span></summary>
        <div style="margin-top:6px;">
          ${children.map(ch => _renderToolTreeNode(ch, depth + 1)).join("")}
        </div>
      </details>`;
          }

          function _renderToolTree(payload) {
            const el = document.getElementById("toolTreeList");
            if (!payload || !payload.tree) {
              el.innerHTML = '<p style="color:var(--muted);font-size:13px;">Kein Register vorhanden.</p>';
              return;
            }
            const tree = payload.tree || {};
            const core = Array.isArray(tree.core) ? tree.core : [];
            const mcpNode = tree.mcp || { kind: "group", name: "mcp", children: [] };
            const skillsNode = tree.skills || { kind: "group", name: "skills", children: [] };
            const coreNode = { kind: "group", name: "core", path: "core", children: core };
            el.innerHTML = [
              _renderToolTreeNode(coreNode, 0),
              _renderToolTreeNode(mcpNode, 0),
              _renderToolTreeNode(skillsNode, 0),
            ].join("");
          }

          async function _loadSkillsTreeFallback() {
            const root = { kind: "group", name: "skills", path: "skills", children: [] };
            try {
              const r = await fetch("/api/skills");
              const d = await r.json();
              if (!d || !d.ok || !Array.isArray(d.items)) return root;
              for (const s of d.items) {
                if (!s || typeof s !== "object") continue;
                const sid = String(s.id || "").trim();
                const sname = String(s.name || sid || "skill").trim();
                if (!sid) continue;
                const tools = Array.isArray(s.tools) ? s.tools : [];
                const children = [];
                for (const t of tools) {
                  if (!t || typeof t !== "object") continue;
                  const kind = String(t.kind || "").trim();
                  if (!kind) continue;
                  children.push({
                    kind: "tool",
                    source: "skill",
                    name: kind,
                    description: `Skill-Tool (${sid})`,
                    skill_id: sid,
                    skill_name: sname,
                    enabled: Boolean(s.enabled),
                  });
                }
                children.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
                root.children.push({
                  kind: "group",
                  name: sname,
                  path: `skills/${sid}`,
                  skill_id: sid,
                  enabled: Boolean(s.enabled),
                  children,
                });
              }
              root.children.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
            } catch (_) {
              return root;
            }
            return root;
          }

          async function toolsTreeLoad(forceRefresh = false) {
            const listEl = document.getElementById("toolTreeList");
            const statusEl = document.getElementById("toolTreeStatus");
            listEl.innerHTML = '<span style="color:var(--muted)">Lade Register…</span>';
            statusEl.textContent = forceRefresh ? "Register wird mit MCP-Refresh geladen…" : "Register wird geladen…";
            try {
              const query = forceRefresh ? "?refresh_mcp=1" : "";
              const r = await fetch(`/api/tools/tree${query}`);
              const d = await r.json();
              if (!d.ok) {
                statusEl.textContent = d.message || "Register konnte nicht geladen werden.";
                listEl.innerHTML = `<p style="color:#ef4444;">${escHtml(statusEl.textContent)}</p>`;
                return;
              }
              d.tree = (d.tree && typeof d.tree === "object") ? d.tree : {};
              d.counts = (d.counts && typeof d.counts === "object") ? d.counts : {};
              if (!d.tree.skills) {
                const skillsFallback = await _loadSkillsTreeFallback();
                d.tree.skills = skillsFallback;
                const skillGroups = Array.isArray(skillsFallback.children) ? skillsFallback.children.length : 0;
                let skillTools = 0;
                for (const g of (skillsFallback.children || [])) {
                  skillTools += Array.isArray(g.children) ? g.children.length : 0;
                }
                if (!Object.prototype.hasOwnProperty.call(d.counts, "skills")) d.counts.skills = skillGroups;
                if (!Object.prototype.hasOwnProperty.call(d.counts, "skill_tools")) d.counts.skill_tools = skillTools;
              }
              _toolTreeData = d;
              const c = d.counts || {};
              const backend = d.backend || {};
              const mcpState = d.mcp_status || {};
              statusEl.textContent = `Core=${c.core || 0}, MCP=${c.mcp || 0}, Skills=${c.skills || 0}, Skill-Tools=${c.skill_tools || 0} · Backend=${backend.backend || "unknown"}${mcpState.ok === false ? ` · MCP: ${mcpState.message || "nicht verfuegbar"}` : ""}`;

              _renderToolTree(d);
            } catch (e) {
              statusEl.textContent = `Fehler: ${e}`;
              listEl.innerHTML = `<p style="color:#ef4444;">${escHtml(String(e))}</p>`;
            }
          }

          function _filterSortMcpTools() {
            const q = String(document.getElementById("mcpToolsSearch").value || "").toLowerCase().trim();
            const typ = String(document.getElementById("mcpToolsType").value || "all");
            const sort = String(document.getElementById("mcpToolsSort").value || "name_asc");
            let items = _mcpToolsData.slice();
            if (q) {
              items = items.filter(t =>
                String(t.name || "").toLowerCase().includes(q) ||
                String(t.description || "").toLowerCase().includes(q) ||
                String(t.server || "").toLowerCase().includes(q)
              );
            }
            if (typ === "external") items = items.filter(t => !t.is_dynamic);
            const cmp = (a, b, key, dir) => {
              const av = String(a[key] || "").toLowerCase();
              const bv = String(b[key] || "").toLowerCase();
              if (av < bv) return dir === "asc" ? -1 : 1;
              if (av > bv) return dir === "asc" ? 1 : -1;
              return 0;
            };
            if (sort === "name_asc") items.sort((a, b) => cmp(a, b, "name", "asc"));
            if (sort === "name_desc") items.sort((a, b) => cmp(a, b, "name", "desc"));
            if (sort === "server_asc") items.sort((a, b) => cmp(a, b, "server", "asc"));
            if (sort === "server_desc") items.sort((a, b) => cmp(a, b, "server", "desc"));
            return items;
          }

          function _renderMcpTools(items) {
            const el = document.getElementById("mcpToolsList");
            if (!items.length) {
              el.innerHTML = '<p style="color:var(--muted);font-size:13px;">Keine MCP-Tools vorhanden.</p>';
              return;
            }
            el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:var(--bg-2);text-align:left;">
          <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Name</th>
          <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Server</th>
          <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Beschreibung</th>
          <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Typ</th>
          <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Aktion</th>
        </tr></thead><tbody>` +
              items.map(t => {
                const typ = t.is_dynamic
                  ? '<span style="color:#22c55e;font-weight:600;">Dynamic</span>'
                  : '<span style="color:var(--muted);">Extern</span>';
                const delBtn = t.is_dynamic
                  ? `<button class="secondary" style="font-size:12px;padding:3px 8px;color:#ef4444;" onclick="mcpToolsDelete('${escHtml(t.name)}')">🗑</button>`
                  : '—';
                return `<tr style="border-bottom:1px solid var(--line);">
            <td style="padding:6px 10px;font-weight:600;">${escHtml(t.name || "?")}</td>
            <td style="padding:6px 10px;">${escHtml(t.server || "—")}</td>
            <td style="padding:6px 10px;color:var(--muted);max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(t.description || "")}">${escHtml(t.description || "—")}</td>
            <td style="padding:6px 10px;">${typ}</td>
            <td style="padding:6px 10px;">${delBtn}</td>
          </tr>`;
              }).join("") + "</tbody></table>";
          }

          async function mcpToolsLoad() {
            const el = document.getElementById("mcpToolsList");
            const st = document.getElementById("mcpToolsStatus");
            el.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
            st.textContent = "";
            try {
              const r = await fetch("/api/mcp/tools");
              const d = await r.json();
              if (!d.ok) {
                _mcpToolsData = [];
                st.textContent = d.message || "MCP nicht verfuegbar.";
                el.innerHTML = `<p style="color:#ef4444;">${escHtml(st.textContent)}</p>`;
                return;
              }
              _mcpToolsData = d.items || [];
              st.textContent = `${_mcpToolsData.length} Tool(s)`;
              _renderMcpTools(_filterSortMcpTools());
              await mcpServersLoad();
              } catch (e) {
              el.innerHTML = `<p style="color:#ef4444;">Fehler: ${escHtml(String(e))}</p>`;
              }
              }

              async function mcpServersLoad() {
              const el = document.getElementById("mcpServersList");
              if (!el) return;
              el.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
              try {
              const r = await fetch("/api/health/mcp");
              const d = await r.json();
              if (!d.ok || !d.servers || d.servers.length === 0) {
                el.innerHTML = '<p style="color:var(--muted);font-size:13px;padding:10px;">Keine externen MCP-Server registriert.</p>';
                return;
              }

              let html = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead><tr style="text-align:left;color:var(--muted);border-bottom:1px solid var(--line);">
                  <th style="padding:6px 10px;">Server Name</th>
                  <th style="padding:6px 10px;">Typ</th>
                  <th style="padding:6px 10px;">Details</th>
                  <th style="padding:6px 10px;text-align:center;">Aktion</th>
                </tr></thead><tbody>`;

              d.servers.forEach(s => {
                html += `<tr style="border-bottom:1px solid var(--line);">
                  <td style="padding:6px 10px;font-weight:600;">${escHtml(s.name)}</td>
                  <td style="padding:6px 10px;">${escHtml(s.type || "stdio")}</td>
                  <td style="padding:6px 10px;color:var(--muted);">${escHtml(s.command || s.base_url || "—")}</td>
                  <td style="padding:6px 10px;text-align:center;">
                    <button class="secondary" style="font-size:12px;padding:3px 8px;color:#ef4444;" onclick="mcpServerDelete('${escHtml(s.name)}')">🗑</button>
                  </td>
                </tr>`;
              });
              html += "</tbody></table>";
              el.innerHTML = html;
              } catch (e) {
              el.innerHTML = `<p style="color:#ef4444;">Fehler: ${escHtml(String(e))}</p>`;
              }
              }

              async function mcpServerDelete(name) {
              if (!confirm(`MCP-Server "${name}" wirklich entfernen?\nAlle Tools dieses Servers werden deaktiviert.`)) return;
              try {
              const r = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, { method: "DELETE" });
              const d = await r.json();
              if (!d.ok) { 
                alert(d.message || "Fehler beim Loeschen."); 
              } else {
                await mcpToolsRefresh();
              }
              } catch (e) {
              alert("Fehler: " + e);
              }
              }

              async function mcpToolsRefresh() {            const st = document.getElementById("mcpToolsStatus");
            st.textContent = "Aktualisiere…";
            try {
              const r = await fetch("/api/mcp/tools/refresh", { method: "POST" });
              const d = await r.json();
              if (!d.ok) {
                st.textContent = d.message || "MCP nicht verfuegbar.";
                return;
              }
              st.textContent = d.message || "Aktualisiert.";
              await mcpToolsLoad();
              await toolsTreeLoad(false);
            } catch (e) {
              st.textContent = `Fehler: ${e}`;
            }
          }

          async function mcpToolsDelete(name) {
            if (!confirm(`MCP-Tool "${name}" wirklich loeschen?`)) return;
            try {
              const r = await fetch(`/api/mcp/tools/${encodeURIComponent(name)}`, { method: "DELETE" });
              const d = await r.json();
              if (!d.ok) { alert(d.message || "Fehler"); }
              await mcpToolsLoad();
              await toolsTreeLoad(false);
            } catch (e) {
              alert("Fehler: " + e);
            }
          }

          // ── MCP Registry ────────────────────────────────────────────────────
          async function mcpRegistrySearch() {
            const q = String(document.getElementById("mcpRegistryQuery").value || "").trim();
            const statusEl = document.getElementById("mcpRegistryStatus");
            const listEl = document.getElementById("mcpRegistryResults");
            const detailsEl = document.getElementById("mcpRegistryDetails");
            detailsEl.style.display = "none";
            detailsEl.textContent = "";
            if (!q) {
              statusEl.textContent = "Bitte Suchbegriff eingeben.";
              listEl.innerHTML = "";
              return;
            }
            statusEl.textContent = "Suche...";
            listEl.innerHTML = "";
            try {
              const r = await fetch(`/api/mcp/registry/search?q=${encodeURIComponent(q)}&limit=20`);
              const d = await r.json();
              if (!d.ok) {
                statusEl.textContent = d.message || "Fehler bei Registry-Suche.";
                return;
              }
              const items = d.items || [];
              statusEl.textContent = `${items.length} Treffer`;
              if (!items.length) {
                listEl.innerHTML = '<p style="color:var(--muted);font-size:13px;">Keine Ergebnisse.</p>';
                return;
              }
              listEl.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:var(--bg-2);text-align:left;">
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Name</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Quelle</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Beschreibung</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Link/Details</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Aktion</th>
          </tr></thead><tbody>` +
                items.map(it => {
                  const name = escHtml(it.name || "");
                  const src = escHtml(it.source_name || it.source_id || "source");
                  const desc = escHtml(it.description || "—");
                  const detail = escHtml(it.detail || "—");
                  const canDetails = String(it.source_type || "").toLowerCase() === "mcp_registry";
                  const isGitHub = String(it.source_type || "").toLowerCase() === "github";
                  const detailBtn = canDetails
                    ? `<button class="secondary" style="font-size:12px;padding:3px 8px;" onclick="mcpRegistryDetails('${escHtml(it.source_id || '')}', '${escHtml(it.name || '')}')">Details</button>`
                    : "";
                  const installBtn = (canDetails || isGitHub)
                    ? `<button class="secondary" style="font-size:12px;padding:3px 8px;margin-left:6px;" onclick="mcpRegistryInstall('${escHtml(it.source_id || '')}', '${escHtml(it.name || '')}')">Einbinden</button>`
                    : "";
                  const downloadBtn = (isGitHub && String(it.detail || '').startsWith('http'))
                    ? `<button class="secondary" style="font-size:12px;padding:3px 8px;margin-left:6px;" onclick="mcpRegistryDownload('${escHtml(it.detail || '')}', '${escHtml(it.name || '')}')">Herunterladen</button>`
                    : "";
                  // Offer a simple "Öffnen" action for entries that include an external link
                  const linkTarget = (it.source_id || it.detail || "") || "";
                  const openBtn = (String(linkTarget).startsWith('http'))
                    ? `<button class="secondary" style="font-size:12px;padding:3px 8px;margin-left:6px;" onclick="window.open('${escHtml(String(linkTarget))}','_blank')">Öffnen</button>`
                    : "";
                  return `<tr style="border-bottom:1px solid var(--line);">
              <td style="padding:6px 10px;font-weight:600;">${name}</td>
              <td style="padding:6px 10px;">${src}</td>
              <td style="padding:6px 10px;color:var(--muted);max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${desc}">${desc}</td>
              <td style="padding:6px 10px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${detail}">${detail}</td>
              <td style="padding:6px 10px;">${detailBtn} ${installBtn} ${downloadBtn} ${openBtn}</td>
            </tr>`;
                }).join("") + "</tbody></table>";
            } catch (e) {
              statusEl.textContent = `Fehler: ${e}`;
            }
          }

          async function mcpRegistryDetails(sourceId, name) {
            const detailsEl = document.getElementById("mcpRegistryDetails");
            detailsEl.style.display = "block";
            detailsEl.textContent = "Lade Details...";
            try {
              const r = await fetch(`/api/mcp/registry/details?source_id=${encodeURIComponent(sourceId)}&name=${encodeURIComponent(name)}`);
              const d = await r.json();
              if (!d.ok) {
                detailsEl.textContent = d.message || "Fehler beim Laden der Details.";
                return;
              }
              const proposal = d.proposal && d.proposal.ok ? d.proposal.server : null;
              if (proposal && proposal.command) {
                detailsEl.textContent = JSON.stringify(
                  { name, proposal, details: d.details },
                  null,
                  2
                );
              } else {
                detailsEl.textContent = JSON.stringify(
                  { name, details: d.details, note: "Kein automatischer Install-Vorschlag. Bitte manuell pruefen." },
                  null,
                  2
                );
              }
            } catch (e) {
              detailsEl.textContent = `Fehler: ${e}`;
            }
          }

          async function mcpRegistryInstall(sourceId, name) {
            if (!confirm(`MCP-Server "${name}" wirklich einbinden?`)) return;
            const st = document.getElementById("mcpRegistryStatus");
            st.innerText = `Installiere "${name}"... Bitte warten (Download/Build)`;
            try {
              const r = await fetch("/api/mcp/registry/install", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source_id: sourceId, name })
              });
              const d = await r.json();
              if (!d.ok) {
                st.innerText = "Fehler bei Installation.";
                alert(d.message || "Install fehlgeschlagen.");
                return;
              }
              st.innerText = "Installation abgeschlossen.";
              alert(d.message || "MCP-Server registriert.");
              await mcpToolsRefresh();
            } catch (e) {
              st.innerText = "Fehler: " + e;
              alert("Fehler: " + e);
            }
          }

          async function mcpRegistryDownload(detailUrl, name) {
            if (!confirm(`Repo "${name}" herunterladen?`)) return;
            const st = document.getElementById("mcpRegistryStatus");
            try {
              st.textContent = "Lade herunter...";
              const r = await fetch(`/api/mcp/registry/download`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ detail: detailUrl, name })
              });
              const d = await r.json();
              if (!d.ok) {
                alert(d.message || "Download fehlgeschlagen.");
                st.textContent = d.message || "Fehler.";
                return;
              }
              alert(d.message || "Download abgeschlossen.");
              st.textContent = d.message || "Heruntergeladen.";
            } catch (e) {
              alert("Fehler: " + e);
              st.textContent = `Fehler: ${e}`;
            }
          }

          async function mcpSourcesLoad() {
            const listEl = document.getElementById("mcpSourcesList");
            listEl.innerHTML = '<span style="color:var(--muted)">Lade…</span>';
            try {
              const r = await fetch("/api/mcp/registry/sources");
              const d = await r.json();
              if (!d.ok) {
                listEl.innerHTML = `<p style="color:#ef4444;">${escHtml(d.message || "Fehler")}</p>`;
                return;
              }
              const items = d.items || [];
              if (!items.length) {
                listEl.innerHTML = '<p style="color:var(--muted);font-size:13px;">Keine Quellen vorhanden.</p>';
                return;
              }
              listEl.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:var(--bg-2);text-align:left;">
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">ID</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Typ</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Base URL</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Aktiv</th>
            <th style="padding:6px 10px;border-bottom:1px solid var(--line);">Aktion</th>
          </tr></thead><tbody>` +
                items.map(it => {
                  const id = escHtml(it.id || "");
                  const typ = escHtml(it.type || "");
                  const base = escHtml(it.base_url || "");
                  const active = it.enabled ? "ja" : "nein";
                  return `<tr style="border-bottom:1px solid var(--line);">
              <td style="padding:6px 10px;font-weight:600;">${id}</td>
              <td style="padding:6px 10px;">${typ}</td>
              <td style="padding:6px 10px;">${base}</td>
              <td style="padding:6px 10px;">${active}</td>
              <td style="padding:6px 10px;">
                <button class="secondary" style="font-size:12px;padding:3px 8px;color:#ef4444;" onclick="mcpSourceDelete('${id}')">🗑</button>
              </td>
            </tr>`;
                }).join("") + "</tbody></table>";
            } catch (e) {
              listEl.innerHTML = `<p style="color:#ef4444;">Fehler: ${escHtml(String(e))}</p>`;
            }
          }

          async function mcpSourceSave() {
            const payload = {
              id: String(document.getElementById("mcpSourceId").value || "").trim(),
              type: String(document.getElementById("mcpSourceType").value || "").trim(),
              name: String(document.getElementById("mcpSourceName").value || "").trim(),
              base_url: String(document.getElementById("mcpSourceBaseUrl").value || "").trim(),
              enabled: String(document.getElementById("mcpSourceEnabled").value || "true") === "true"
            };
            if (!payload.id || !payload.type || !payload.base_url) {
              alert("id, type und base_url sind erforderlich.");
              return;
            }
            try {
              const r = await fetch("/api/mcp/registry/sources", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
              });
              const d = await r.json();
              if (!d.ok) {
                alert(d.message || "Fehler beim Speichern.");
                return;
              }
              await mcpSourcesLoad();
            } catch (e) {
              alert("Fehler: " + e);
            }
          }

          async function mcpSourceDelete(id) {
            if (!confirm(`Quelle "${id}" wirklich loeschen?`)) return;
            try {
              const r = await fetch(`/api/mcp/registry/sources/${encodeURIComponent(id)}`, { method: "DELETE" });
              const d = await r.json();
              if (!d.ok) {
                alert(d.message || "Fehler beim Loeschen.");
                return;
              }
              await mcpSourcesLoad();
            } catch (e) {
              alert("Fehler: " + e);
            }
          }
          document.getElementById("mcpToolsRefreshBtn").addEventListener("click", mcpToolsRefresh);
          document.getElementById("toolTreeReloadBtn").addEventListener("click", () => toolsTreeLoad(true));
          document.getElementById("mcpRegistrySearchBtn").addEventListener("click", mcpRegistrySearch);
          document.getElementById("mcpSourceSaveBtn").addEventListener("click", mcpSourceSave);
          document.getElementById("mcpSourceReloadBtn").addEventListener("click", mcpSourcesLoad);
          document.getElementById("mcpToolsSearch").addEventListener("input", () => _renderMcpTools(_filterSortMcpTools()));
          document.getElementById("mcpToolsType").addEventListener("change", () => _renderMcpTools(_filterSortMcpTools()));
          document.getElementById("mcpToolsSort").addEventListener("change", () => _renderMcpTools(_filterSortMcpTools()));

          // Self-Improve Tab beim Wechsel laden
          const _origSwitchTab = switchTab;
          switchTab = function (name) {
            _origSwitchTab(name);
            if (name === "selfimprove") { siLoadPatches(); siLoadReports(); }
            if (name === "logs") { loadErrorLog(); }
            if (name === "scripts") { scriptsLoad(); }
            if (name === "mcp") {
              mcpToolsRefresh();
              mcpSourcesLoad();
            }
          };

          // Sidebar Navigation
          document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
              const panel = item.dataset.panel;

              // Update active nav
              document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
              item.classList.add('active');

              // Update active panel
              document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
              const targetPanel = document.getElementById('panel-' + panel);
              if (targetPanel) {
                targetPanel.classList.add('active');
              }

              // Update title (keep emoji)
              const titleText = item.textContent.trim();
              document.getElementById('panelTitle').textContent = titleText;

              // Update tab buttons (visual only, no click trigger)
              document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
              const tab = document.querySelector('[data-tab="' + panel + '"]');
              if (tab) {
                tab.classList.add('active');
              }

              // Load data for specific panels
              if (panel === 'status') {
                loadMeta();
                loadConfigView();
              } else if (panel === 'llm') {
                loadCatalog();
                loadConfigView();
                updateAddModelProviderDropdown();
              } else if (panel === 'selfimprove') {
                siLoadPatches();
                siLoadReports();
              } else if (panel === 'memory') {
                loadMemory();
                loadFacts();
              } else if (panel === 'skills') {
                loadSkills();
              } else if (panel === 'logs') {
                loadAuditLog();
              } else if (panel === 'tools') {
                loadToolLog();
              } else if (panel === 'queue') {
                refreshQueueStats();
              } else if (panel === 'mcp') {
                mcpToolsRefresh();
                mcpSourcesLoad();
              } else if (panel === 'timeouts') {
                loadTimeoutsConfig();
              }
            });
          });
// Expose functions to global window object for onclick handlers
window.siLoadPatches = siLoadPatches;
window.siLoadReports = siLoadReports;
window.siApplyPatch = siApplyPatch;
window.siRejectPatch = siRejectPatch;
window.siRestorePatch = siRestorePatch;
window.siShowDetail = siShowDetail;
window.siDeleteReport = siDeleteReport;
window.siDeleteAllReports = siDeleteAllReports;
window.switchTab = switchTab;
window.siStatusBadge = siStatusBadge;
window.siRiskBadge = siRiskBadge;
window.escHtml = escHtml;
window.fmtTs = fmtTs;
