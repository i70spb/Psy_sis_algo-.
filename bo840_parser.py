#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BO840 Markdown Parser
Парсит markdown-файлы библиотеки и строит graph.json для алгоритмической обработки.

Использование:
    python bo840_parser.py /path/to/Psy_sis_8.1 /path/to/output/graph.json

Требования: Python 3.7+, рекомендуется PyYAML (pip install pyyaml)
"""

import sys
import os
import re
import json
from pathlib import Path
from datetime import datetime

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("WARNING: PyYAML не установлен. Front matter парсится упрощённо.")


class BO840Parser:
    """Парсер markdown-репозитория БО840"""

    # Распознаваемые типы сущностей по префиксам тегов
    TYPE_MAP = {
        "аксиома": "axiom",
        "переменная": "variable", 
        "ось": "axis",
        "механика": "mechanic",
        "эмоция": "emotion",
        "ловушка": "trap",
        "детское_правило": "childhood_rule",
        "метод": "method",
        "протокол": "protocol",
        "кейс": "case",
        "концепт": "concept",
    }

    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)
        self.graph = {
            "meta": {
                "version": "3.1",
                "date": datetime.now().isoformat(),
                "source_repo": str(self.repo_path.name),
                "description": "Автоматически сгенерированный граф БО840"
            },
            "schema": {
                "node_types": list(self.TYPE_MAP.values()) + ["concept"],
                "levels": ["L0", "L1", "L2", "L3", "L4", "L5"],
                "statuses": ["draft", "hypothesis", "approved"],
                "relation_types": ["closes", "closed_by", "shifts_up", "shifts_down",
                                  "diagnoses", "source_of", "leads_to", "part_of", "requires"]
            },
            "nodes": {},
            "cases": {},
            "index": {
                "by_tag": {},
                "by_file": {},
                "by_type": {}
            }
        }

    def parse_front_matter(self, content):
        """Извлекает YAML front matter из начала файла"""
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        fm_text = parts[1].strip()
        body = parts[2].strip()

        if HAS_YAML:
            try:
                return yaml.safe_load(fm_text) or {}, body
            except yaml.YAMLError:
                pass

        # Упрощённый парсер если PyYAML нет
        fm = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip().strip('"').strip("'")
        return fm, body

    def extract_tags(self, text):
        """Извлекает все теги формата #префикс_название"""
        pattern = r'#([а-яa-z0-9_]+_[а-яa-z0-9_]+)'
        return list(set(re.findall(pattern, text)))

    def extract_sections(self, body):
        """Извлекает секции по заголовкам markdown"""
        sections = {}
        current_section = "_intro"
        current_content = []

        for line in body.split("\n"):
            if line.startswith("## ") or line.startswith("### "):
                sections[current_section] = "\n".join(current_content).strip()
                current_section = line.lstrip("# ").strip()
                current_content = []
            else:
                current_content.append(line)

        sections[current_section] = "\n".join(current_content).strip()
        return sections

    def detect_type(self, node_id, front_matter=None):
        """Определяет тип узла по ID или front matter"""
        if front_matter and "type" in front_matter:
            return front_matter["type"]

        for prefix, ntype in self.TYPE_MAP.items():
            if node_id.startswith(prefix):
                return ntype
        return "concept"

    def add_node(self, node_id, node_data):
        """Добавляет узел в граф и обновляет индексы"""
        if node_id in self.graph["nodes"]:
            print(f"WARNING: Дублирование узла {node_id}, пропускаем")
            return

        self.graph["nodes"][node_id] = node_data

        # Индекс по типу
        ntype = node_data.get("type", "unknown")
        self.graph["index"]["by_type"].setdefault(ntype, []).append(node_id)

        # Индекс по файлу
        src = node_data.get("source_file", "unknown")
        self.graph["index"]["by_file"].setdefault(src, []).append(node_id)

        # Индекс по тегам
        for tag in node_data.get("tags", []):
            tag_clean = tag.lstrip("#")
            self.graph["index"]["by_tag"].setdefault(tag_clean, []).append(node_id)

    def parse_file(self, filepath):
        """Парсит один markdown-файл"""
        rel_path = filepath.relative_to(self.repo_path)
        content = filepath.read_text(encoding="utf-8")

        front_matter, body = self.parse_front_matter(content)
        tags = self.extract_tags(content)
        sections = self.extract_sections(body)

        # Ищем карточки сущностей по заголовкам ### #тег_название
        entity_pattern = r'###\s+#([а-яa-z0-9_]+)\s*[—\-]?\s*(.*)'

        found_entities = 0
        for match in re.finditer(entity_pattern, body):
            node_id = match.group(1)
            title = match.group(2).strip()

            # Определяем тип
            node_type = self.detect_type(node_id, front_matter)

            # Извлекаем секцию до следующего заголовка
            start_pos = match.end()
            next_match = re.search(r'###\s+#', body[start_pos:])
            if next_match:
                section_text = body[start_pos:start_pos + next_match.start()].strip()
            else:
                section_text = body[start_pos:].strip()

            node_data = {
                "type": node_type,
                "title": title,
                "status": front_matter.get("status", "draft"),
                "level": front_matter.get("level", ""),
                "content": section_text[:500] + "..." if len(section_text) > 500 else section_text,
                "tags": [f"#{t}" for t in tags if node_id in t or t.startswith("БО840")],
                "relations": [],
                "source_file": str(rel_path)
            }

            # Дополнительные поля по типу
            if "**Корневое правило:**" in section_text:
                rule_match = re.search(r'\*\*Корневое правило:\*\*(.*?)(?:

|
\*\*)', section_text, re.DOTALL)
                if rule_match:
                    node_data["core_rule"] = rule_match.group(1).strip()

            if "**Механика:**" in section_text:
                mech_match = re.search(r'\*\*Механика:\*\*(.*?)(?:

|
\*\*)', section_text, re.DOTALL)
                if mech_match:
                    node_data["mechanics"] = mech_match.group(1).strip()

            self.add_node(node_id, node_data)
            found_entities += 1

        # Если не нашли карточек — файл может быть описательным (оси, переменные)
        if found_entities == 0 and front_matter.get("type") == "axis":
            # Особый случай: файл осей
            node_id = rel_path.stem.lower().replace("_", "")
            self.add_node(node_id, {
                "type": "axis_file",
                "title": front_matter.get("title", str(rel_path)),
                "status": front_matter.get("status", "draft"),
                "level": front_matter.get("level", ""),
                "content": body[:1000],
                "tags": [f"#{t}" for t in tags],
                "relations": [],
                "source_file": str(rel_path)
            })

        return found_entities

    def parse_all(self):
        """Парсит все markdown-файлы в репозитории"""
        md_files = list(self.repo_path.rglob("*.md"))
        print(f"Найдено markdown-файлов: {len(md_files)}")

        total_entities = 0
        for md_file in md_files:
            if ".git" in str(md_file):
                continue
            count = self.parse_file(md_file)
            total_entities += count
            if count > 0:
                print(f"  {md_file.name}: {count} сущностей")

        print(f"\nВсего узлов: {len(self.graph['nodes'])}")
        print(f"По типам: {dict((k, len(v)) for k, v in self.graph['index']['by_type'].items())}")

        return self.graph

    def save(self, output_path):
        """Сохраняет граф в JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.graph, f, ensure_ascii=False, indent=2)
        print(f"\nГраф сохранён: {output_path}")
        size = os.path.getsize(output_path)
        print(f"Размер: {size:,} байт")


def main():
    if len(sys.argv) < 2:
        print("Использование: python bo840_parser.py <путь_к_репо> [выходной_файл]")
        print("Пример: python bo840_parser.py ./Psy_sis_8.1 ./graph.json")
        sys.exit(1)

    repo_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "graph.json"

    if not os.path.isdir(repo_path):
        print(f"ERROR: {repo_path} не является директорией")
        sys.exit(1)

    parser = BO840Parser(repo_path)
    parser.parse_all()
    parser.save(output_path)


if __name__ == "__main__":
    main()
