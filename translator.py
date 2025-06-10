import deepl

class DeepLTranslator():
    def __init__(self, api_key):
        self.dtranslator = None
        try:
            self.dtranslator = deepl.Translator(api_key)
            print("[Translator] Initialized DeepL Translator!")
        except deepl.exceptions.DeepLException as e:
            raise Exception("Failed to initalize DeepL!", e)
    
    def convert_language(self, lang_code: str, specific = False) -> str:
        """
        Convert a language code to the format used by DeepL.
        """
        if specific and lang_code.upper().startswith('EN-'):
            return lang_code.upper()

        return lang_code[:2].upper()

    def translate(self, source_lang, target_lang, text) -> str:
        output = None
        try:
            source = self.convert_language(source_lang)
            target = self.convert_language(target_lang, True)
            print(f"[Translator] Translating from {source} to {target}...")
            output = self.dtranslator.translate_text(text=text, source_lang=source, target_lang=target)
            print(f"[Translator] {text} -> {output.text}")
        except Exception as e:
            raise Exception("Failed to translate text!", e)
        if output is not None:
            return output.text
        else:
            return ""