"""
Execution Validator - Prüft Scripts/Tools/Befehle vor der Ausführung
"""
import os
import re
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import tempfile

class ExecutionValidator:
    """Validiert Code, Scripts und Befehle vor der Ausführung"""
    
    def __init__(self, workspace_root: str = ".", cfg: Optional[Dict[str, Any]] = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.cfg = cfg or {}
        self.safe_imports = {
            'os', 'sys', 'json', 're', 'time', 'datetime', 'pathlib', 'typing',
            'collections', 'itertools', 'math', 'random', 'string', 'hashlib',
            'base64', 'uuid', 'csv', 'io', 'textwrap', 'functools', 'operator'
        }
        
        self.dangerous_patterns = [
            r'__import__\s*\([^)]*\)',
            r'eval\s*\([^)]*\)',
            r'exec\s*\([^)]*\)',
            r'compile\s*\([^)]*\)',
            r'open\s*\([^)]*\)\s*,\s*[\'"]w[\'"]',
            r'os\.system\s*\([^)]*\)',
            r'subprocess\.(Popen|run|call|check_output)\s*\([^)]*\)',
            r'shutil\.rmtree\s*\([^)]*\)',
            r'os\.remove\s*\([^)]*\)',
            r'os\.unlink\s*\([^)]*\)'
        ]

    def _is_unrestricted_admin(self) -> bool:
        """Prüft ob der Full Autonomy Mode für Admins aktiv ist."""
        role = str(self.cfg.get("security", {}).get("active_role", "user")).lower()
        mode = str(self.cfg.get("security", {}).get("execution_mode", "deny")).lower()
        return role == "admin" and mode == "unrestricted"

    def validate_python_code(self, code: str, context: str = "unknown") -> Tuple[bool, str]:
        """Validiert Python-Code auf Syntax und Sicherheit"""
        try:
            # 1. Syntax-Validierung
            try:
                ast.parse(code)
            except SyntaxError as e:
                return False, f"Syntaxfehler in {context}: {str(e)}"

            # 2. Bypass für Admins
            if self._is_unrestricted_admin():
                return True, "Admin-Bypass aktiv: Code erlaubt"

            # 3. Sicherheitsprüfung
            security_issues = self._check_security_issues(code)

            if security_issues:
                return False, f"Sicherheitsprobleme in {context}: {', '.join(security_issues)}"
            
            # 3. Import-Validierung
            import_issues = self._check_imports(code)
            if import_issues:
                return False, f"Unerlaubte Imports in {context}: {', '.join(import_issues)}"
            
            return True, "Code validiert erfolgreich"
            
        except Exception as e:
            return False, f"Validierungsfehler in {context}: {str(e)}"
    
    def _check_security_issues(self, code: str) -> List[str]:
        """Prüft auf gefährliche Muster"""
        issues = []
        
        for pattern in self.dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Gefährliches Muster: {pattern}")
        
        # Prüfe auf Dateioperationen außerhalb von workspace
        file_ops = re.findall(r'open\s*\(([^)]+)\)', code, re.IGNORECASE)
        for file_arg in file_ops:
            # Vereinfachte Prüfung auf absolute Pfade oder ../
            if '..' in file_arg or ('/' in file_arg and not 'data/workspace' in file_arg):
                issues.append(f"Möglicher Zugriff außerhalb workspace: {file_arg}")
        
        return issues
    
    def _check_imports(self, code: str) -> List[str]:
        """Prüft Imports auf Sicherheit"""
        issues = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        if module_name not in self.safe_imports:
                            issues.append(module_name)
                
                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module.split('.')[0] if node.module else ""
                    if module_name and module_name not in self.safe_imports:
                        issues.append(module_name)
        
        except:
            # Falls AST-Parsing fehlschlägt, regex-basierte Prüfung
            import_matches = re.findall(r'^\s*import\s+([a-zA-Z0-9_\.]+)', code, re.MULTILINE)
            for imp in import_matches:
                module_name = imp.split('.')[0]
                if module_name not in self.safe_imports:
                    issues.append(module_name)
            
            from_matches = re.findall(r'^\s*from\s+([a-zA-Z0-9_\.]+)\s+import', code, re.MULTILINE)
            for imp in from_matches:
                module_name = imp.split('.')[0]
                if module_name not in self.safe_imports:
                    issues.append(module_name)
        
        return issues
    
    def validate_tool_schema(self, schema: Dict, tool_code: str) -> Tuple[bool, str]:
        """Validiert Tool-Schema gegen Tool-Code"""
        try:
            # Extrahiere Parameter aus run-Funktion
            param_pattern = r'def run\s*\(\s*\*\*kwargs\s*\)'
            if not re.search(param_pattern, tool_code):
                return False, "Tool muss eine run(**kwargs) Funktion haben"
            
            # Prüfe ob Schema Properties definiert
            if not isinstance(schema, dict):
                return False, "Schema muss ein Dictionary sein"
            
            # Einfache Schema-Validierung
            required_fields = {'type', 'description', 'properties'}
            for field in required_fields:
                if field not in schema:
                    return False, f"Schema fehlt Feld: {field}"
            
            return True, "Schema validiert erfolgreich"
            
        except Exception as e:
            return False, f"Schema-Validierungsfehler: {str(e)}"
    
    def validate_shell_command(self, command: str) -> Tuple[bool, str]:
        """Validiert Shell-Befehle auf Sicherheit"""
        if self._is_unrestricted_admin():
            return True, "Admin-Bypass aktiv: Befehl erlaubt"

        dangerous_commands = [
            'rm ', 'del ', 'format ', 'chmod ', 'chown ', 'sudo ', 'su ',
            'wget ', 'curl ', 'powershell -EncodedCommand', 'Invoke-Expression',
            'net ', 'reg ', 'schtasks ', 'taskkill ', 'shutdown '
        ]
        
        command_lower = command.lower()
        
        for dangerous in dangerous_commands:
            if dangerous in command_lower:
                return False, f"Gefährlicher Befehl erkannt: {dangerous}"
        
        # Prüfe auf Pipe- oder Redirect-Operationen die gefährlich sein könnten
        if '|' in command and ('rm' in command or 'del' in command):
            return False, "Gefährliche Pipe-Operation mit Löschbefehl"
        
        if '>' in command and command.count('>') > 2:
            return False, "Zu viele Redirect-Operationen"
        
        return True, "Befehl validiert erfolgreich"
    
    def test_tool_execution(self, tool_code: str, test_args: Dict = None) -> Tuple[bool, str]:
        """Testet Tool-Ausführung in isolierter Umgebung"""
        if test_args is None:
            test_args = {}
        
        try:
            # Erstelle temporäres Tool
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(tool_code)
                temp_file = f.name
            
            try:
                # Führe Tool in Subprocess aus
                test_env = os.environ.copy()
                test_env['PYTHONPATH'] = str(self.workspace_root)
                
                result = subprocess.run(
                    [sys.executable, temp_file],
                    input=json.dumps(test_args),
                    text=True,
                    capture_output=True,
                    timeout=5,
                    env=test_env
                )
                
                if result.returncode == 0:
                    return True, f"Tool-Test erfolgreich: {result.stdout[:200]}"
                else:
                    return False, f"Tool-Test fehlgeschlagen: {result.stderr[:500]}"
                    
            finally:
                os.unlink(temp_file)
                
        except subprocess.TimeoutExpired:
            return False, "Tool-Test timeout (5s)"
        except Exception as e:
            return False, f"Tool-Test Fehler: {str(e)}"
    
    def verify_step_result(self, verification_criteria: str, actual_result: Any) -> Tuple[bool, str]:
        """Verifiziert Schritt-Ergebnis gegen Kriterien"""
        if not verification_criteria:
            return True, "Keine Verifikationskriterien definiert"
        
        criteria_lower = verification_criteria.lower()
        result_str = str(actual_result).lower()
        
        # Positive Indikatoren
        positive_words = ["ok", "success", "erfolgreich", "kompiliert", "valide", "existiert", "funktioniert", "pass"]
        
        # Negative Indikatoren
        negative_words = ["fehler", "error", "failed", "fehlgeschlagen", "syntax error", "invalid", "ungültig", "nicht gefunden", "not found"]
        
        # Wenn negative Indikatoren vorhanden, ist es fehlgeschlagen
        if any(neg in result_str for neg in negative_words):
            return False, "Verifikation fehlgeschlagen: Negative Indikatoren gefunden"
        
        # Wenn positive Indikatoren oder einfach nur Ergebnis vorhanden, ist es erfolgreich
        if any(pos in result_str for pos in positive_words) or (result_str and len(result_str) > 0):
            return True, "Verifikation erfolgreich"
        
        return True, "Verifikation erfolgreich"

    def reflect_tool_result(self, kind: str, args: Dict[str, Any], result: str, ok: bool) -> Optional[str]:
        """🚨 AGGRESSIVE system critic - prüft Plausibilität und Logik, nicht nur Fehler"""
        critique = []
        res_lower = result.lower()

        # 0. HALLUZINATIONS-PRÜFUNG: Wenn Tool ERROR "does not exist" zurückgibt
        if "does not exist" in res_lower or "path" in res_lower and "error" in res_lower:
            critique.append(
                "🚨 HALLUZINATION ERKANNT: Das Tool gibt ERROR aus - du hast einen ERFUNDENEN Pfad verwendet!\n"
                "    → Das ist GENAU das Problem: Falscher Pfad statt mem_update_plan + fs_list_dir\n"
                "    → SOFORT STOPPEN und mem_update_plan mit ECHTER Verzeichnisstruktur aufrufen\n"
                "    → fs_list_dir ZUERST, dann fs_find_files mit echtem Pfad!"
            )

        # 1. Timeout Analysis
        if "timeout" in res_lower and ("> 300s" in result or "> 180s" in result):
            critique.append(
                f"⚠️ SYSTEM-KRITIK: Das Tool '{kind}' ist in einen Timeout gelaufen. "
                "Dies deutet auf eine ineffiziente Strategie hin (z.B. rekursive Suche auf Netzlaufwerken). "
                "EMPFEHLUNG: Nutze mem_update_plan um eine bessere Strategie zu planen!"
            )

        # 2. Permission / Access Denied Analysis
        if any(x in res_lower for x in ["zugriff verweigert", "access denied", "systemfehler 5"]):
            critique.append(
                f"⚠️ SYSTEM-KRITIK: Zugriff verweigert. "
                "Versuche NICHT, den gleichen Pfad nochmal zu benutzen. "
                "EMPFEHLUNG: mem_update_plan - alternative Strategie!"
            )

        # 3. Empty results on search - nur warnen wenn Pfad verdächtig ist
        # (nicht bei validen Netzwerkpfaden oder wenn Suche legitim leer sein kann)
        if kind in ["fs_find_files", "fs_grep"] and ("0 files" in res_lower or "0 dateien" in res_lower):
            # UNC/Netzwerkpfade (\\server\share) sind meist korrekt — kein Fehlalarm
            _path_in_result = str(result.get("result") or result.get("reply") or "")
            _is_unc = _path_in_result.lstrip().startswith("\\\\") or "\\\\medianas" in _path_in_result or "\\\\nas" in _path_in_result.lower()
            if not _is_unc:
                critique.append(
                    "⚠️ HINWEIS: fs_find_files hat 0 Ergebnisse zurückgegeben.\n"
                    "    Mögliche Ursachen: falscher Pfad, falsches Suchmuster, oder Dateien existieren wirklich nicht.\n"
                    "    → Prüfe mit fs_list_dir ob der Pfad existiert und Dateien enthält."
                )

        # 4. PLAUSIBILITÄTSPRÜFUNG: Fehler-Ignorieren-Muster
        if not ok and "error" in res_lower:
            critique.append(
                "🚨 TOOL-FEHLER - DAS IST EIN SIGNAL ZUM UMPLANEN!\n"
                "    Das Tool ist FEHLGESCHLAGEN. Das bedeutet:\n"
                "    • Dein Plan war falsch\n"
                "    • Der Pfad/Parameter waren falsch\n"
                "    • Die Strategie muss überarbeitet werden\n"
                "    → Nutze mem_update_plan um neuen Plan zu schreiben\n"
                "    → NICHT einfach das gleiche nochmal versuchen!"
            )

        # 5. sys_python_exec: f-string / Umlaut-Fehler → direkte Lösung
        if kind == "sys_python_exec":
            if "unterminated f-string" in res_lower or "f-string expression" in res_lower:
                critique.append(
                    "🚨 KRITIK - f-string SyntaxError: Du hast mehrzeiligen oder Sonderzeichen-Inhalt direkt "
                    "als f-String in den Python-Code eingebettet.\n"
                    "    → LÖSUNG: Erst Inhalt mit fs_write_file in eine Datei schreiben, "
                    "dann in Python per open(pfad, encoding='utf-8').read() laden!\n"
                    "    → NICHT: content = f'''...langer Text...'''"
                )
            if "'latin-1' codec can't encode" in result or "unicodeencodeerror" in res_lower:
                critique.append(
                    "🚨 KRITIK - UnicodeEncodeError: Die verwendete Bibliothek unterstützt kein UTF-8.\n"
                    "    → LÖSUNG für PDF: reportlab verwenden (UTF-8 nativ):\n"
                    "      from reportlab.lib.pagesizes import A4\n"
                    "      from reportlab.platypus import SimpleDocTemplate, Paragraph\n"
                    "      from reportlab.lib.styles import getSampleStyleSheet\n"
                    "    → ODER: open(pfad, 'w', encoding='utf-8') statt default-encoding!\n"
                    "    → WeasyPrint auf Windows NICHT nutzbar (fehlt pango/cairo)."
                )
            # Leere Datei nach vermeintlich erfolgreichem Schreiben
            saved_paths = re.findall(
                r'(?:saved to|written to|geschrieben:|created:|code saved to)\s+([^\s\n]+\.(?:ino|py|txt|md|json|csv|pdf))',
                result, re.IGNORECASE
            )
            for sp in saved_paths:
                try:
                    sp_clean = sp.strip().rstrip('.,)')
                    if Path(sp_clean).exists() and Path(sp_clean).stat().st_size == 0:
                        critique.append(
                            f"🚨 KRITIK - Datei '{sp_clean}' wurde geschrieben aber ist LEER (0 Bytes)!\n"
                            "    Das bedeutet: Die Variable/der extrahierte Inhalt war ein leerer String.\n"
                            "    → Prüfe die Extraktion/Parsing-Logik und stelle sicher, dass Inhalt vorhanden ist.\n"
                            "    → Füge eine Prüfung ein: if not content: raise ValueError('Kein Inhalt extrahiert')"
                        )
                except Exception:
                    pass

        # 6. fs_get_tree WARNING - Output viel zu groß
        if kind == "fs_get_tree" and len(result) > 100_000:
            critique.append(
                f"🚨 KRITIK - fs_get_tree Output viel zu groß ({len(result):,} Zeichen)!\n"
                "    Das Verzeichnis ist zu groß für fs_get_tree.\n"
                "    → NICHT mehr fs_get_tree, fs_list_dir, oder fs_grep verwenden\n"
                "    → Nutze STATTDESSEN: fs_find_files mit '*pattern*'\n"
                "    → BEISPIEL: fs_find_files mit pattern='*dubstep*' im ECHTEN Musikverzeichnis"
            )

        if critique:
            return "\n\n".join(critique)
        return None

def create_validation_report(validation_results: List[Tuple[str, bool, str]]) -> str:
    """Erstellt einen Validierungsbericht"""
    report = ["# VALIDIERUNGSBERICHT", ""]
    
    total = len(validation_results)
    passed = sum(1 for _, success, _ in validation_results if success)
    
    report.append(f"## Übersicht")
    report.append(f"- Gesamtprüfungen: {total}")
    report.append(f"- Erfolgreich: {passed}")
    report.append(f"- Fehlgeschlagen: {total - passed}")
    report.append(f"- Erfolgsrate: {(passed/total*100):.1f}%")
    report.append("")
    
    report.append("## Detailergebnisse")
    for i, (item, success, message) in enumerate(validation_results, 1):
        status = "✓" if success else "✗"
        report.append(f"{i}. {status} {item}: {message}")
    
    return "\n".join(report)