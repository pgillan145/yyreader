
import minorimpact.config

yyreader_config = minorimpact.config.getConfig(script_name = 'yyreader')

wsgi_app = 'yyreader.server:app'
bind = f'0.0.0.0:{yyreader_config['server']['port']}'

if (yyreader_config['server']['log_file']):
    errorlog = yyreader_config['server']['log_file']

if (eval(yyreader_config['server']['debug'])):
    loglevel = "DEBUG"


