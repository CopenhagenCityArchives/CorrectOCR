import pymysql
import json

from ._super import TokenList


@TokenList.register('db')
class DBTokenList(TokenList):
    def save(self, name: str):
        connection = pymysql.connect(
            host=self.config.db_host,
            user=self.config.db_user,
            password=self.config.db_password,
            db=self.config.db,
            charset='utf-8')
        try:
            with connection.cursor() as cursor:
                for token in self:
                    cursor.execute(
                        "INSERT INTO token (file_id, file_index, original, gold, bin, heuristic, decision, selection, token_type, token_info) "
                        "VALUES (%(file_id)s, %(file_index)s, %(original)s, %(gold)s,%(bin)s, %(decision)s, %(selection)s, %(token_type)s, %(token_info)s) "
                        "ON DUPLICATE KEY UPDATE "
                        "  original=%(original)s,"
                        "  gold=%(gold)s,"
                        "  bin=%(bin)s,"
                        "  decision=%(decision)s,"
                        "  selection=%(selection)s,"
                        "  token_type=%(token_type)s,"
                        "   token_info=%(token_info)s", {
                            'file_id': token.fileid,
                            'file_index': token.index,
                            'orignal': token.original,
                            'gold': token.gold,
                            'bin': token.bin,
                            'decision': token.decision,
                            'selection': token.selection,
                            'token_type': token.__class__.__name__,
                            'token_info': json.dumps(token.token_info)
                        })
            connection.commit()
        finally:
            connection.close()

    def load(self, fileid: str):
        from .. import Token
        connection = pymysql.connect(
            host=self.config.host,
            user=self.config.password,
            db=self.config.db,
            charset='utf-8',
            cursorClass=pymysql.cursors.DictCursor)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM token WHERE file_id = %(file_id)s ORDER BY file_index",
                    {'file_id': fileid})
                for result in cursor.fetchall():
                    cursor.execute(
                        "SELECT * FROM kbest WHERE file_id = %s AND file_index = %s ORDER BY k",
                        (result['file_id'], result['file_index']))
                    kbest = cursor.fetchall()
                    token_dict = {
                        'Token type': result['token_type'],
                        'File ID': result['file_id'],
                        'Index': result['file_index'],
                        'Gold': result['gold'],
                        'Bin': result['bin'],
                        'Heuristic': result['heuristic'],
                        'Selection': result['selection'],
                        'Decision': result['decision']
                    }
                    for best in kbest:
                        token_dict[f"{best['k']}-best"] = best['candidate']
                        token_dict[f"{best['k']}-best prob."] = best[
                            'probability']
                    self.append(Token.from_dict(token_dict))
        finally:
            connection.close()
