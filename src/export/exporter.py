import pandas as pd

def export_table(df:pd.DataFrame, path:str):
  if path.lower().endswith('.csv'): df.to_csv(path,index=False,encoding='utf-8-sig')
  elif path.lower().endswith('.xlsx'): df.to_excel(path,index=False)
  elif path.lower().endswith('.json'): df.to_json(path,force_ascii=False,orient='records',indent=2)
  else: raise ValueError('Unsupported export format')
