# create_all_indicators.py
import os
import sys

# Lista completa de indicadores baseada nas estratégias
indicators = [
    "OBV",
    "ATR",
    "Aroon",
    "MFI",
    "CMF",
    "Chaikin Oscillator",
    "Elder Ray",
    "Force Index",
    "Keltner Channel",
    "Donchian Channel",
    "Pivot Points",
    "PPO",
    "ROC",
    "Ultimate Oscillator",
    "Volume-Weighted Average Price (VWAP)",
    "Williams Alligator",
    "Fractals",
    "Gator Oscillator",
    "Accelerator Oscillator",
    "Awesome Oscillator",
    "Detrended Price Oscillator",
    "Market Facilitation Index",
    "Schaff Trend Cycle",
    "Ehler Fisher Transform",
    "Fisher Transform",
    "Hilbert Transform",
    "Zero-Lag Moving Average",
    "Arnaud Legoux Moving Average",
    "Triangular Moving Average",
    "KAMA",
    "VIDYA",
    "T3 Moving Average",
    "TEMA",
    "WMA",
    "Hull Moving Average",
    "ALMA",
    "Linear Regression",
    "Time Series Forecast",
    "Moving Average Envelope",
    "Price Channels",
    "PSAR",
    "Donchian Channels",
    "Keltner Channels",
    "Ichimoku Cloud",
    "Aroon Oscillator",
    "Chande Momentum Oscillator",
    "True Strength Index",
    "Elder Force Index"
]

# Função para formatar o nome do arquivo a partir do nome do indicador
def format_file_name(name):
    return name.lower().replace(" ", "_").replace("-", "_").replace("%", "percent").replace("(", "").replace(")", "")

# Função para formatar o nome da função a partir do nome do indicador
def format_function_name(name):
    # Para nomes com caracteres especiais, manter o formato correto
    special_names = {
        "OBV": "obv",
        "ATR": "atr",
        "VWAP": "vwap",
        "PPO": "ppo",
        "ROC": "roc",
        "ALMA": "alma",
        "KAMA": "kama",
        "VIDYA": "vidya",
        "TEMA": "tema",
        "WMA": "wma",
        "PSAR": "psar",
        "CMF": "cmf",
        "MFI": "mfi"
    }
    
    # Se o nome está no dicionário de nomes especiais, use-o
    for key, value in special_names.items():
        if key in name and len(name) == len(key):
            return value
    
    # Para outros casos, converter para camelCase
    words = name.replace("-", " ").split()
    result = words[0].lower()
    for i in range(1, len(words)):
        # Verificar se a palavra está no dicionário de nomes especiais
        word_upper = words[i].upper()
        if word_upper in special_names:
            result += special_names[word_upper]
        else:
            result += words[i].capitalize()
    
    return result

# Definir os parâmetros e retornos para indicadores específicos
indicator_params = {
    "OBV": "data",
    "ATR": "data, period=14",
    "Aroon": "data, period=14",
    "MFI": "data, period=14",
    "CMF": "data, period=20",
    "Chaikin Oscillator": "data, fast_period=3, slow_period=10",
    "Elder Ray": "data, period=13",
    "Force Index": "data, period=13",
    "Keltner Channel": "data, period=14, atr_period=10, multiplier=2.0, use_ema=True",
    "Donchian Channel": "data, period=20",
    "Pivot Points": "data, pivot_type='standard'",
    "PPO": "data, fast_period=12, slow_period=26, signal_period=9",
    "ROC": "data, period=12",
    "Ultimate Oscillator": "data, period1=7, period2=14, period3=28",
    "Volume-Weighted Average Price (VWAP)": "data, period=14, reset_daily=True",
    "Williams Alligator": "data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3",
    "Fractals": "data, window=2",
    "Gator Oscillator": "data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3",
    "Accelerator Oscillator": "data, sma_period=5, ao_period_fast=5, ao_period_slow=34",
    "Awesome Oscillator": "data, fast_period=5, slow_period=34",
    "Detrended Price Oscillator": "data, period=14, sma_period=15",
    "Market Facilitation Index": "data",
    "Schaff Trend Cycle": "data, stc_fast=23, stc_slow=50, stc_cycle=10, use_close=True",
    "Ehler Fisher Transform": "data, period=10",
    "Fisher Transform": "data, period=10",
    "Hilbert Transform": "data, period=14",
    "Zero-Lag Moving Average": "data, period=14, use_close=True",
    "Arnaud Legoux Moving Average": "data, period=14, sigma=6.0, offset=0.85, use_close=True",
    "Triangular Moving Average": "data, period=14, use_close=True",
    "KAMA": "data, period=14, fast_ema=2, slow_ema=30",
    "VIDYA": "data, period=14, chande_period=10, use_close=True",
    "T3 Moving Average": "data, period=14, volume_factor=0.7, use_close=True",
    "TEMA": "data, period=14, use_close=True",
    "WMA": "data, period=14, use_close=True",
    "Hull Moving Average": "data, period=14, use_close=True",
    "ALMA": "data, period=14, sigma=6.0, offset=0.85, use_close=True",
    "Linear Regression": "data, period=14, use_close=True",
    "Time Series Forecast": "data, period=14, forecast_periods=1, use_close=True",
    "Moving Average Envelope": "data, period=14, envelope_percentage=2.5, use_ema=False",
    "Price Channels": "data, period=20",
    "PSAR": "data, af_start=0.02, af_increment=0.02, af_max=0.2",
    "Donchian Channels": "data, period=20",
    "Keltner Channels": "data, period=14, atr_period=10, multiplier=2.0, use_ema=True",
    "Ichimoku Cloud": "data, tenkan_period=9, kijun_period=26, senkou_span_b_period=52, displacement=26",
    "Aroon Oscillator": "data, period=14",
    "Chande Momentum Oscillator": "data, period=14, use_close=True",
    "True Strength Index": "data, r_period=25, s_period=13, signal_period=7, use_close=True",
    "Elder Force Index": "data, period=13"
}

# Definir os retornos esperados para cada indicador
indicator_returns = {
    "OBV": "obv: Série com os valores do On Balance Volume",
    "ATR": "atr: Série com os valores do Average True Range",
    "Aroon": "aroon_up, aroon_down, aroon_oscillator: Séries com os valores do Aroon Up, Aroon Down e Aroon Oscillator",
    "MFI": "mfi: Série com os valores do Money Flow Index",
    "CMF": "cmf: Série com os valores do Chaikin Money Flow",
    "Chaikin Oscillator": "chaikin_oscillator: Série com os valores do Chaikin Oscillator",
    "Elder Ray": "bull_power, bear_power: Séries com os valores do Bull Power e Bear Power",
    "Force Index": "force_index: Série com os valores do Force Index",
    "Keltner Channel": "middle_line, upper_band, lower_band: Séries com os valores das bandas de Keltner",
    "Donchian Channel": "upper_band, middle_band, lower_band: Séries com os valores das bandas de Donchian",
    "Pivot Points": "pivot, s1, s2, s3, r1, r2, r3: Séries com os valores dos níveis de pivot",
    "PPO": "ppo, ppo_signal, ppo_histogram: Séries com os valores do PPO",
    "ROC": "roc: Série com os valores do Rate of Change",
    "Ultimate Oscillator": "ultimate_oscillator: Série com os valores do Ultimate Oscillator",
    "Volume-Weighted Average Price (VWAP)": "vwap, upper_band, lower_band: Séries com os valores do VWAP e suas bandas",
    "Williams Alligator": "jaw, teeth, lips: Séries com os valores dos componentes do Williams Alligator",
    "Fractals": "fractal_up, fractal_down: Séries com os valores dos fractais",
    "Gator Oscillator": "jaw_teeth, teeth_lips: Séries com os valores do Gator Oscillator",
    "Accelerator Oscillator": "accelerator_oscillator: Série com os valores do Accelerator Oscillator",
    "Awesome Oscillator": "awesome_oscillator: Série com os valores do Awesome Oscillator",
    "Detrended Price Oscillator": "dpo: Série com os valores do Detrended Price Oscillator",
    "Market Facilitation Index": "mfi: Série com os valores do Market Facilitation Index",
    "Schaff Trend Cycle": "stc: Série com os valores do Schaff Trend Cycle",
    "Ehler Fisher Transform": "fisher_transform: Série com os valores do Ehler Fisher Transform",
    "Fisher Transform": "fisher_transform: Série com os valores do Fisher Transform",
    "Hilbert Transform": "ht_sine, ht_leadsine, ht_trend: Séries com os componentes do Hilbert Transform",
    "Zero-Lag Moving Average": "zlema: Série com os valores do ZLEMA",
    "Arnaud Legoux Moving Average": "alma: Série com os valores do ALMA",
    "Triangular Moving Average": "tma: Série com os valores do TMA",
    "KAMA": "kama: Série com os valores do KAMA",
    "VIDYA": "vidya: Série com os valores do VIDYA",
    "T3 Moving Average": "t3: Série com os valores do T3 Moving Average",
    "TEMA": "tema: Série com os valores do TEMA",
    "WMA": "wma: Série com os valores do WMA",
    "Hull Moving Average": "hma: Série com os valores do Hull Moving Average",
    "ALMA": "alma: Série com os valores do ALMA",
    "Linear Regression": "linear_reg: Série com os valores da regressão linear",
    "Time Series Forecast": "tsf: Série com os valores do Time Series Forecast",
    "Moving Average Envelope": "middle, upper, lower: Séries com os valores do Moving Average Envelope",
    "Price Channels": "upper, lower: Séries com os valores dos canais de preço",
    "PSAR": "psar: Série com os valores do Parabolic SAR",
    "Donchian Channels": "upper_band, middle_band, lower_band: Séries com os valores das bandas de Donchian",
    "Keltner Channels": "middle_line, upper_band, lower_band: Séries com os valores das bandas de Keltner",
    "Ichimoku Cloud": "tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span: Séries com os componentes do Ichimoku Cloud",
    "Aroon Oscillator": "aroon_oscillator: Série com os valores do Aroon Oscillator",
    "Chande Momentum Oscillator": "cmo: Série com os valores do Chande Momentum Oscillator",
    "True Strength Index": "tsi, tsi_signal: Séries com os valores do TSI e sua linha de sinal",
    "Elder Force Index": "force_index: Série com os valores do Elder Force Index"
}

# Template para o conteúdo do arquivo
template = """import pandas as pd
import numpy as np

def {function_name}({params}):
    \"\"\"
    Calcula o indicador {display_name}
    
    Parâmetros:
    {param_description}
    
    Retorno:
    {return_description}
    \"\"\"
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{{col}}' não encontrada nos dados")
    
    # TODO: Implementar o cálculo do indicador {display_name}
    
    # Código-base para iniciar a implementação
    
    return {return_values}
"""

# Criar pasta de indicadores se não existir
os.makedirs("indicators", exist_ok=True)

# Criar arquivo para cada indicador
for indicator in indicators:
    file_name = format_file_name(indicator)
    function_name = format_function_name(indicator)
    file_path = f"indicators/{file_name}.py"
    
    # Obter os parâmetros específicos do indicador
    params = indicator_params.get(indicator, "data, period=14")
    
    # Gerar descrição dos parâmetros
    param_lines = []
    for param in params.split(", "):
        name_part = param.split("=")[0]
        param_lines.append(f"- {name_part}: Descrição do parâmetro")
    param_description = "\n    ".join(param_lines)
    
    # Obter os valores de retorno esperados
    return_description = indicator_returns.get(indicator, "Série com os valores do indicador")
    
    # Determinar os valores de retorno para o return statement
    if "," in return_description:
        return_values = ", ".join([r.split(":")[0].strip() for r in return_description.split(",")])
    else:
        return_values = return_description.split(":")[0].strip()
    
    # Criar o conteúdo do arquivo
    content = template.format(
        function_name=function_name,
        params=params,
        display_name=indicator,
        param_description=param_description,
        return_description=return_description,
        return_values=return_values
    )
    
    # Escrever o arquivo com codificação UTF-8
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Arquivo criado: {file_path}")

print("\nTodos os arquivos de indicadores foram criados com sucesso!\n")

# Gerando código para adicionar ao Indicators.py
with open("indicators_class_code.py", "w", encoding="utf-8") as f:
    f.write("# Código para adicionar ao arquivo Indicators.py\n\n")
    
    # Adicionar imports
    f.write("# Adicionar os imports dos novos indicadores\n")
    for indicator in indicators:
        file_name = format_file_name(indicator)
        function_name = format_function_name(indicator)
        
        f.write(f"try:\n")
        f.write(f"    from .{file_name} import {function_name}\n")
        f.write("except (ImportError, AttributeError):\n")
        
        # Gerar função de fallback
        params = indicator_params.get(indicator, "data, period=14")
        f.write(f"    def {function_name}({params}):\n")
        f.write(f"        # Placeholder para o indicador\n")
        
        # Gerar valores de retorno do fallback
        if "," in indicator_returns.get(indicator, ""):
            returns = [r.split(":")[0].strip() for r in indicator_returns.get(indicator, "").split(",")]
            return_values = ", ".join([f"pd.Series(index=data.index)" for _ in returns])
            f.write(f"        return {return_values}\n\n")
        else:
            f.write(f"        return pd.Series(index=data.index)\n\n")
    
    # Adicionar métodos à classe Indicators
    f.write("\n# Adicionar os métodos à classe Indicators\n")
    f.write("class Indicators:\n")
    f.write("    # Adicionar ao final da classe os novos métodos\n\n")
    
    for indicator in indicators:
        function_name = format_function_name(indicator)
        # Formatar nome do método (para casos especiais como OBV, VWAP, etc.)
        special_prefixes = {
            "obv": "getOBV",
            "atr": "getATR",
            "vwap": "getVWAP",
            "ppo": "getPPO",
            "roc": "getROC",
            "alma": "getALMA",
            "kama": "getKAMA",
            "vidya": "getVIDYA",
            "tema": "getTEMA",
            "wma": "getWMA",
            "psar": "getPSAR",
            "cmf": "getCMF",
            "mfi": "getMFI"
        }
        
        # Verificar se o nome da função está em special_prefixes
        if function_name in special_prefixes:
            method_name = special_prefixes[function_name]
        else:
            # Converter para camelCase com get prefixo
            method_name = "get" + function_name[0].upper() + function_name[1:]
        
        f.write(f"    @staticmethod\n")
        params = indicator_params.get(indicator, "data, period=14")
        f.write(f"    def {method_name}({params}):\n")
        param_names = [p.split("=")[0] for p in params.split(", ")]
        f.write(f"        return {function_name}({', '.join(param_names)})\n\n")

print("Código para atualizar a classe Indicators foi gerado em 'indicators_class_code.py'")