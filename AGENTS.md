# AGENTS

Repo-local agent rules for `mid`.

- Use the local `.venv` for all Python commands.
- Do not install Python packages globally.
- Before claiming a format is supported, validate a real conversion flow (not only unit mocks).
- Keep temporary artifacts out of the repo root and tracked paths.

Project-local skills available in this repo:

<available_skills>
  <skill>
    <name>mid-cli</name>
    <description>Trigger: mid, MarkItDown, convert document to markdown, .docx, .pdf, batch conversion. Use this skill when an agent needs to run or validate the mid CLI correctly.</description>
    <location>file:///D:/MisProyectos/mid/skills/mid-cli/SKILL.md</location>
  </skill>
</available_skills>
