"""
Программа для отправки документов через API Диадок
"""
import os
import base64
from pathlib import Path
from typing import Dict, Optional
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class DiadocClient:
    """Клиент для работы с API Диадок"""

    def __init__(self):
        self.api_client_id = os.getenv('DIADOC_API_CLIENT_ID')
        self.login = os.getenv('DIADOC_LOGIN')
        self.password = os.getenv('DIADOC_PASSWORD')
        self.api_url = os.getenv('DIADOC_API_URL', 'https://diadoc-api.kontur.ru')
        self.token = None

        if not all([self.api_client_id, self.login, self.password]):
            raise ValueError(
                "Не все обязательные переменные окружения установлены. "
                "Проверьте .env файл (DIADOC_API_CLIENT_ID, DIADOC_LOGIN, DIADOC_PASSWORD)"
            )

    def authenticate(self) -> str:
        """
        Аутентификация в API Диадок
        Возвращает токен авторизации
        """
        url = f"{self.api_url}/V3/Authenticate"

        headers = {
            "Authorization": f"DiadocAuth ddauth_api_client_id={self.api_client_id}",
            "Content-Type": "application/json"
        }

        params = {
            "type": "password"
        }

        data = {
            "login": self.login,
            "password": self.password
        }

        print("Аутентификация...")
        response = requests.post(url, headers=headers, params=params, json=data)

        if response.status_code == 200:
            self.token = response.text.strip('"')
            print("✓ Аутентификация успешна")
            return self.token
        else:
            raise Exception(f"Ошибка аутентификации: {response.status_code} - {response.text}")

    def get_auth_headers(self) -> Dict[str, str]:
        """Получить заголовки с авторизацией"""
        if not self.token:
            self.authenticate()

        return {
            "Authorization": f"DiadocAuth ddauth_api_client_id={self.api_client_id}, ddauth_token={self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_box_id_by_inn_kpp(self, inn: str, kpp: Optional[str] = None) -> Dict:
        """
        Получить BoxId организации по ИНН и КПП

        Args:
            inn: ИНН организации
            kpp: КПП организации (опционально)

        Returns:
            Словарь с информацией об организации и BoxId
        """
        url = f"{self.api_url}/GetOrganizationsByInnKpp"

        params = {"inn": inn}
        if kpp:
            params["kpp"] = kpp

        headers = self.get_auth_headers()

        print(f"Поиск организации по ИНН: {inn}" + (f", КПП: {kpp}" if kpp else ""))
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get('Organizations') and len(data['Organizations']) > 0:
                org = data['Organizations'][0]
                print(f"✓ Найдена организация: {org.get('ShortName', org.get('FullName'))}")
                return org
            else:
                raise Exception(f"Организация с ИНН {inn}" + (f" и КПП {kpp}" if kpp else "") + " не найдена")
        else:
            raise Exception(f"Ошибка поиска организации: {response.status_code} - {response.text}")

    def send_document(
            self,
            from_inn: str,
            to_inn: str,
            document_path: str,
            from_kpp: Optional[str] = None,
            to_kpp: Optional[str] = None,
            comment: Optional[str] = None,
            need_recipient_signature: bool = True,
            document_date: Optional[str] = None
    ) -> Dict:
        """
        Отправить неформализованный документ

        Args:
            from_inn: ИНН отправителя
            to_inn: ИНН получателя
            document_path: Путь к файлу документа
            from_kpp: КПП отправителя (опционально)
            to_kpp: КПП получателя (опционально)
            comment: Комментарий к документу
            need_recipient_signature: Требуется ли подпись получателя (по умолчанию True)
            document_date: Дата документа в формате ДД.ММ.ГГГГ (опционально)

        Returns:
            Информация об отправленном сообщении
        """
        # Получаем BoxId отправителя
        from_org = self.get_box_id_by_inn_kpp(from_inn, from_kpp)
        from_box_id = from_org['Boxes'][0]['BoxIdGuid']

        # Получаем BoxId получателя
        to_org = self.get_box_id_by_inn_kpp(to_inn, to_kpp)
        to_box_id = to_org['Boxes'][0]['BoxIdGuid']

        # Читаем файл документа
        doc_path = Path(document_path)
        if not doc_path.exists():
            raise FileNotFoundError(f"Файл не найден: {document_path}")

        with open(doc_path, 'rb') as f:
            content = f.read()

        content_base64 = base64.b64encode(content).decode('utf-8')

        # Формируем сообщение для отправки неформализованного документа
        # БЕЗ подписи (документ потребует подписания вручную в Диадоке)

        # Обязательное поле - имя файла
        metadata = [
            {"Key": "FileName", "Value": doc_path.name}
        ]

        # Добавляем дату документа, если указана
        if document_date:
            metadata.append({"Key": "DocumentDate", "Value": document_date})

        message_data = {
            "FromBoxId": from_box_id,
            "ToBoxId": to_box_id,
            "DocumentAttachments": [
                {
                    "TypeNamedId": "Nonformalized",  # Тип документа - неформализованный
                    "SignedContent": {
                        "Content": content_base64
                        # Signature отсутствует - документ будет отправлен без подписи
                    },
                    "Metadata": metadata,
                    "NeedRecipientSignature": need_recipient_signature,
                    "Comment": comment
                }
            ]
        }

        url = f"{self.api_url}/V3/PostMessage"
        headers = self.get_auth_headers()

        print(f"\nОтправка документа: {doc_path.name}")
        print(f"От: {from_org.get('ShortName')} (BoxId: {from_box_id})")
        print(f"Кому: {to_org.get('ShortName')} (BoxId: {to_box_id})")

        response = requests.post(url, headers=headers, json=message_data)

        if response.status_code == 200:
            result = response.json()
            message_id = result.get('MessageId')
            print(f"✓ Документ успешно отправлен!")
            print(f"  MessageId: {message_id}")
            print(f"\n⚠ ВАЖНО: Документ требует подписания в веб-интерфейсе Диадок")
            print(f"  или через API с использованием ЭЦП")
            if need_recipient_signature:
                print(f"  ✓ Запрошена ответная подпись получателя")
            return result
        else:
            error_text = response.text
            print(f"✗ Ошибка отправки: {response.status_code}")
            print(f"  Детали: {error_text}")
            raise Exception(f"Ошибка отправки документа: {response.status_code} - {error_text}")


def main():
    """Основная функция программы"""

    # =====================================================
    # НАСТРОЙКИ ОТПРАВКИ (измените под свои данные)
    # =====================================================

    # ИНН и КПП отправителя (вашей компании)
    FROM_INN = "7827004830"  # Замените на ваш ИНН
    FROM_KPP = None  # Укажите КПП если требуется, или оставьте None

    # ИНН и КПП получателя
    TO_INN = "7839305479"  # Замените на ИНН получателя
    TO_KPP = None  # Укажите КПП если требуется, или оставьте None

    # Путь к документу для отправки
    DOCUMENT_PATH = "test.docx"

    # Дополнительные параметры
    COMMENT = "Соглашение об ЭДО"
    DOCUMENT_DATE = "18.11.2025"  # Дата в формате ДД.ММ.ГГГГ
    NEED_SIGNATURE = True  # Запросить ответную подпись получателя

    # =====================================================

    try:
        client = DiadocClient()

        result = client.send_document(
            from_inn=FROM_INN,
            to_inn=TO_INN,
            document_path=DOCUMENT_PATH,
            from_kpp=FROM_KPP,
            to_kpp=TO_KPP,
            comment=COMMENT,
            document_date=DOCUMENT_DATE,
            need_recipient_signature=NEED_SIGNATURE
        )

        print("\n" + "=" * 60)
        print("ОТПРАВКА ЗАВЕРШЕНА УСПЕШНО")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"\n✗ ОШИБКА: {e}")
        print("  Убедитесь, что файл существует в указанном месте")
    except ValueError as e:
        print(f"\n✗ ОШИБКА КОНФИГУРАЦИИ: {e}")
        print("  Создайте файл .env на основе .env.example")
    except Exception as e:
        print(f"\n✗ ОШИБКА: {e}")


if __name__ == "__main__":
    main()