#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import requests
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

FOCUS_BASE = "https://focus-api.kontur.ru/api3"
API_KEY = os.getenv('API_KEY')

def get_json(url: str, params: dict) -> Any:
    params = {**params, "key": API_KEY}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def canonicalize_position(pos: str) -> str:
    p = pos.strip().lower()
    if "генераль" in p and "директор" in p:
        return "Генеральный директор"
    if "директор" in p:
        return "Директор"
    return pos.strip().capitalize()

def join_fio_from_parts(person: Dict[str, Any]) -> Optional[str]:
    parts = []
    for k in ("lastName", "firstName", "middleName"):
        v = person.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts) if parts else None

def extract_from_ul(ul: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    # Основной путь: UL.heads[0]
    heads = ul.get("heads")
    if isinstance(heads, list) and heads:
        h = heads[0] if isinstance(heads[0], dict) else None
        if h:
            pos = h.get("position") or h.get("post") or h.get("role")
            fio = h.get("fio") or h.get("name") or h.get("fullName")
            if pos and fio:
                return canonicalize_position(pos), fio
    # Альтернатива: UL.management{post,fio}
    mgmt = ul.get("management") or ul.get("manager") or ul.get("generalManager")
    if isinstance(mgmt, dict):
        pos = mgmt.get("post") or mgmt.get("position") or mgmt.get("role")
        fio = mgmt.get("fio") or mgmt.get("name") or mgmt.get("fullName")
        if pos and fio:
            return canonicalize_position(pos), fio
    return None

def extract_from_ip(ip: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    # Для ИП выводим только "ИП ФИО"
    fio = None
    if isinstance(ip.get("fio"), str):
        fio = ip["fio"]
    elif isinstance(ip.get("structuredFio"), dict):
        fio = join_fio_from_parts(ip["structuredFio"])
    else:
        fio = join_fio_from_parts(ip)
    if fio:
        return "ИП", fio  # <- специальная метка для форматирования вывода
    return None

def deep_scan(node: Any, acc: List[Tuple[str, str]]):
    if isinstance(node, dict):
        if "UL" in node and isinstance(node["UL"], dict):
            m = extract_from_ul(node["UL"])
            if m:
                acc.append(m)
        if "IP" in node and isinstance(node["IP"], dict):
            m = extract_from_ip(node["IP"])
            if m:
                acc.append(m)
        # как последний резерв — общая пара (position/fio)
        pos = node.get("position") or node.get("post") or node.get("role")
        fio = node.get("fio") or node.get("name") or node.get("fullName")
        if isinstance(pos, str) and isinstance(fio, str):
            acc.append((canonicalize_position(pos), fio))
        for v in node.values():
            deep_scan(v, acc)
    elif isinstance(node, list):
        for item in node:
            deep_scan(item, acc)

def get_head_by_inn(inn: str) -> Tuple[str, str]:
    # /req
    data = get_json(f"{FOCUS_BASE}/req", {"inn": inn})
    root = data[0] if isinstance(data, list) and data else data
    if isinstance(root, dict):
        if isinstance(root.get("UL"), dict):
            m = extract_from_ul(root["UL"])
            if m:
                return m
        if isinstance(root.get("IP"), dict):
            m = extract_from_ip(root["IP"])
            if m:
                return m
    # /egrDetails
    data = get_json(f"{FOCUS_BASE}/egrDetails", {"inn": inn})
    root = data[0] if isinstance(data, list) and data else data
    if isinstance(root, dict):
        if isinstance(root.get("UL"), dict):
            m = extract_from_ul(root["UL"])
            if m:
                return m
        if isinstance(root.get("IP"), dict):
            m = extract_from_ip(root["IP"])
            if m:
                return m
        # последний шанс
        acc: List[Tuple[str, str]] = []
        deep_scan(root, acc)
        if acc:
            return acc[0]
    raise RuntimeError("Не удалось найти данные о руководителе в ответах API.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python contur_focus.py <ИНН>")
        sys.exit(2)
    inn = sys.argv[1].strip()
    try:
        position, fio = get_head_by_inn(inn)
        # формат вывода
        if position == "ИП":
            print(f"ИП {fio}")
        else:
            print(f"{position} {fio}")
    except requests.HTTPError as e:
        print(f"HTTP ошибка от API: {e.response.status_code if e.response else ''} {e.response.text if e.response else e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
