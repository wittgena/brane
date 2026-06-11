# anchor.emit.folding.issue
## @lineage: meta.flow.emit.folding.issue
## @lineage: meta.flow.folding.issue
## @lineage: meta.flow.emit.issue.summary
import _thread
import argparse
import httpx
import json
import os
import re
from pathlib import Path
from typing import Dict, Any
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path
from frame.scope.manager import managed_scope

log = get_emitter('issue.summary')
ISSUE_WORKSPACE = resolve_path("workspace") / "issue"
REGISTRY_FILE = ISSUE_WORKSPACE / "registry.jsonl"
REPORT_PATH = ISSUE_WORKSPACE / "report"

class IssueSummary:
    """@desc: Analyzes conversations from a specific target URL and realigns topology via LLM."""
    def __init__(self, engine_factory: callable, github_token: str = None):
        self.engine_factory = engine_factory
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Surgent-IssueAnalyzer/1.5"
        }
        token = github_token or os.getenv("GITHUB_TOKEN")
        if token:
            self.headers["Authorization"] = f"token {token}"
            
        self.intercepted_text = ""
        self.response_count = 0

    def _rupture_callback(self, event):
        """Intercepts stream; severs connection when meaningful JSON is completed"""
        if event.source != "agent": return

        self.response_count += 1
        
        if self.response_count % 50 == 0:
            log.debug(f"## @monitor: Received {self.response_count} tokens...")

        if self.response_count >= 1000:
            log.error("## @fatal: Max token limit (1000) reached.")
            _thread.interrupt_main()
            return

        text = event.content.strip()
        # 중첩 JSON이 없을 때만 안전하게 동작하도록 프롬프트에서 Flat JSON을 강제함
        if len(text) > 30 and "}" in text: 
            self.intercepted_text = text
            log.warning("## @rupture: JSON payload completed. Severing loop.")
            _thread.interrupt_main()

    def _fetch_conversations(self, owner: str, repo: str, issue_number: str) -> str:
        """Extracts issue body and comments with a limit of 5."""
        issue_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        comments_url = f"{issue_url}/comments"
        log.info(f"  └─ Extracting conversations: {issue_url}")
        
        try:
            conversations = []
            with httpx.Client(headers=self.headers) as client:
                # 1. 이슈 본문(Description) 가져오기
                issue_resp = client.get(issue_url)
                if issue_resp.status_code == 200:
                    data = issue_resp.json()
                    body = data.get("body") or "No description provided."
                    user = data.get("user", {}).get("login", "Author")
                    conversations.append(f"[{user}] (Issue Body): {body}")

                # 2. 코멘트(Comments) 가져오기
                comments_resp = client.get(comments_url)
                if comments_resp.status_code == 200:
                    for comment in comments_resp.json():
                        body = comment.get("body", "")
                        user = comment.get("user", {}).get("login", "Commenter")
                        conversations.append(f"[{user}]: {body}")

            total_conv = len(conversations)
            conv_text = ""
            
            # 3. 최대 5개까지만 추출
            for idx, conv in enumerate(conversations[:5], 1):
                conv_text += f"\n--- 대화 {idx} ---\n{conv}\n"
            
            # 4. 5개 초과 시 생략 표시 추가
            if total_conv > 5:
                omitted_count = total_conv - 5
                conv_text += f"\n... 외 {omitted_count}개의 대화 생략됨 ...\n"
                
            return conv_text or "No conversation found."
        except Exception as e:
            log.error(f"  └─ Exception during Conversation API request: {e}")
            return "Failed to fetch conversation information."

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extracts and parses JSON from intercepted text."""
        if not text:
            return {"error": "No response intercepted from LLM.", "raw": ""}

        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            log.error(f"JSON parsing failed: {e}")
        
        return {"error": "JSON parsing failed", "raw": text.strip()}

    def _manifest_analysis(self, target_json: Dict[str, Any]) -> Dict[str, Any]:
        """Deep analysis pipeline for a single target."""
        url = target_json.get("url", "")
        if not url:
            log.error("Target JSON missing 'url' field.")
            return target_json

        try:
            parts = url.split("github.com/")[1].split("/")
            owner, repo, type_, number = parts[0], parts[1], parts[2], parts[3]
        except IndexError:
            log.error(f"URL parsing failed: {url}")
            return target_json

        # 원본 대화 내용 추출 및 저장 (Appendix 용)
        conversation_context = self._fetch_conversations(owner, repo, number)
        target_json["raw_conversations"] = conversation_context

        log.info("  └─ Requesting topological analysis from engine...")
        
        prompt = f"""
        You are a lead architect analyzing system structures and issue trackers.
        Analyze the following GitHub target's title and conversations.

        [Target Title]: {target_json.get('title')}
        [URL]: {url}
        [Conversations]:
        {conversation_context}

        Output STRICTLY in JSON format with the following 4 keys. 
        IMPORTANT: All values MUST be translated and written in Korean (한국어). Do NOT use nested JSON objects.
        {{
            "translated_conversations": "제공된 5개 이하의 대화 내용을 한국어로 요약 및 번역 (마크다운 리스트 형식 텍스트)",
            "symptom": "이슈의 표면적인 현상 (1줄 요약)",
            "cause": "구조적/기술적 근본 원인 (1줄 요약)",
            "tech_stack": "핵심 기술 스택 및 요구 역량 (1줄 요약)"
        }}
        """

        self.intercepted_text = ""
        self.response_count = 0
        engine = self.engine_factory("analyzer")

        try:
            response = engine.ask(prompt, callback=self._rupture_callback)
            if not self.intercepted_text and response:
                self.intercepted_text = response if isinstance(response, str) else str(response)
                log.debug("  └─ Used direct return value instead of callback stream.")
        except KeyboardInterrupt:
            log.info(f"  └─ Analysis phase severed by Rupture.")

        refined_summary = self._extract_json(self.intercepted_text)
        
        target_json["summary"] = refined_summary
        return target_json

    def _generate_individual_report(self, item: Dict[str, Any]):
        """Generates a dedicated markdown report file for the specific issue."""
        REPORT_PATH.mkdir(parents=True, exist_ok=True)
        
        issue_id = item.get('issue_id', 'unknown_issue')
        target_file = REPORT_PATH / f"{issue_id}.md"
        
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(f"# GitHub Issue Analysis: {issue_id}\n\n")
            f.write(f"## {item.get('title')}\n")
            f.write(f"- **URL**: {item.get('url')}\n")
            f.write(f"- **Tag**: {item.get('tag')}\n\n")
            
            summary = item.get("summary", {})
            if "error" in summary:
                f.write(f"> **분석 실패**: {summary.get('error')}\n\n")
            else:
                f.write("### 💬 대화 요약 (Translated)\n")
                f.write(f"{summary.get('translated_conversations', '대화 내역 없음')}\n\n")
                
                f.write("### 🔍 분석 요약 (LLM Summary)\n")
                f.write(f"- **증상(Symptom)**: {summary.get('symptom', 'N/A')}\n")
                f.write(f"- **원인(Cause)**: {summary.get('cause', 'N/A')}\n")
                f.write(f"- **기술 스택(Tech Stack)**: {summary.get('tech_stack', 'N/A')}\n")
            
            # Appendix: 원본 대화 내용 추가
            f.write("\n---\n\n")
            f.write("## 📎 Appendix: 원본 대화 내역 (Raw Conversations)\n\n")
            f.write("```text\n")
            f.write(f"{item.get('raw_conversations', '원본 대화 내역을 불러오지 못했습니다.')}\n")
            f.write("```\n")
                
        log.info(f"  └─ Report generated at: {target_file}")

    def run(self, target_id: str):
        """Main execution process targeting a specific ID in registry.jsonl"""
        log.info("===")
        log.info(f"## @daemon: surgent deep_scan (Target ID: {target_id})")
        log.info("===")

        if not REGISTRY_FILE.exists():
            log.error(f"Registry file does not exist: {REGISTRY_FILE}")
            return

        target_found = False
        analyzed_result = None
        updated_lines = []

        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line: continue
            
            try:
                data = json.loads(line)
                if data.get("issue_id") == target_id:
                    log.info(f"Target confirmed in registry: {target_id}")
                    data = self._manifest_analysis(data)
                    analyzed_result = data
                    target_found = True
                
                # raw_conversations 같은 임시 데이터는 registry.jsonl에 저장하지 않으려면 
                # 여기서 pop 처리할 수 있으나, 이력 추적을 위해 그대로 둡니다.
                updated_lines.append(json.dumps(data, ensure_ascii=False) + "\n")
            except json.JSONDecodeError:
                updated_lines.append(line + "\n")

        if not target_found:
            log.warning(f"Target ID '{target_id}' not found in {REGISTRY_FILE}.")
            return

        # 1. registry.jsonl 업데이트
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
            
        # 2. 마크다운 리포트 생성 ({id}.md)
        if analyzed_result:
            self._generate_individual_report(analyzed_result)

        log.info("=" * 60)
        log.info(f"Analyzer complete. Registry updated.")
        
        summary = analyzed_result.get('summary', {})
        if "error" not in summary:
            log.info("  [요약 생성 완료]")
        else:
            log.error("  [!] Analysis Failed.")
        log.info("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Issue Summary (Targeted Conversations Mode)")
    parser.add_argument("--id", type=str, required=True, help="Target ID (must match an issue_id in registry.jsonl)")
    args = parser.parse_args()

    with managed_scope(use_was=False, show_logs=True) as server:
        engine_factory = server.get_engine() 
        analyzer = IssueSummary(engine_factory=engine_factory)
        analyzer.run(args.id)

if __name__ == "__main__":
    main()