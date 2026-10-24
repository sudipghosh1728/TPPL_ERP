"""Local, rules-based named-entity extraction; suggestions require human review."""
import io,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
PATTERNS={
 'PAINT_SYSTEM':r'\b(?:epoxy|polyurethane|polyester|zinc[- ]rich|alkyd|acrylic|primer|powder coat(?:ing)?|hot dip galvani[sz](?:ed|ing))\b',
 'COLOUR':r'\bRAL\s*[-:]?\s*\d{4}\b',
 'COATING_THICKNESS':r'\b(?:DFT\s*[:=]?\s*\d+(?:\s*[-–]\s*\d+)?\s*(?:microns?|µm|um)?|\d+\s*(?:microns?|µm))\b',
 'SURFACE_PREPARATION':r'\b(?:SA\s*2[.,]5|SA\s*[23]|SSPC[- ]SP\s*\d+)\b',
 'MATERIAL_GRADE':r'\b(?:IS\s*2062(?:\s*[A-Z]\s*\d+\s*[A-Z]*)?|ASTM\s*[A-Z]\s*\d+(?:\s*GR\.?\s*[A-Z0-9]+)?|S(?:235|275|355|420|460)[A-Z0-9+]*|SS\s*(?:304|316)[L]?|EN\s*10025(?:-\d)?)\b',
 'CERTIFICATE':r'\b(?:EN\s*10204\s*3[.,][12]|MTC|test certificate|ultrasonic test(?:ing)?|impact test(?:ing)?|UT\s*(?:test|required))\b',
 'DIMENSION':r'\b\d+(?:\.\d+)?\s*[xX×]\s*\d+(?:\.\d+)?(?:\s*[xX×]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|m)?\b'
}
def entities(text):
 out=[]
 for label,pattern in PATTERNS.items():
  for m in re.finditer(pattern,text,re.I):
   start=text.rfind('\n',0,m.start())+1;end=text.find('\n',m.end());end=len(text) if end<0 else end
   out.append(dict(label=label,value=m.group(),start=m.start(),end=m.end(),context=text[start:end][:500]))
 return sorted(out,key=lambda e:e['start'])[:300]
def extract(raw,name):
 ext=Path(name).suffix.lower()
 if ext in ('.txt','.csv'):return raw.decode('utf-8-sig',errors='replace')[:150000]
 if ext=='.pdf':
  if not raw.startswith(b'%PDF-'):raise ValueError('Not a readable PDF')
  from pypdf import PdfReader
  reader=PdfReader(io.BytesIO(raw));parts=[]
  if len(reader.pages)>50:raise ValueError('PO exceeds 50 pages; enter specifications manually')
  for page in reader.pages:
   contents=page.get_contents()
   if contents and len(contents.get_data())>8*1024*1024:raise ValueError('PO page is too complex; enter specifications manually')
   parts.append(page.extract_text() or '')
  return '\n'.join(parts)[:150000]
 if ext in ('.docx','.xlsx'):
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if sum(i.file_size for i in z.infolist())>20*1024*1024:raise ValueError('Expanded document exceeds 20 MB')
   if ext=='.docx':return '\n'.join(n.text or '' for n in ET.fromstring(z.read('word/document.xml')).iter() if n.tag.endswith('}t'))[:150000]
  from openpyxl import load_workbook
  wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
  try:return '\n'.join(' '.join(str(v) for v in row if v is not None) for ws in wb for row in ws.iter_rows(max_row=3000,max_col=40,values_only=True))[:150000]
  finally:wb.close()
 return ''
def suggestions(raw,name):
 try:
  text=extract(raw,name);found=entities(text)
  painting='\n'.join(dict.fromkeys(e['context'] for e in found if e['label'] in ('PAINT_SYSTEM','COLOUR','COATING_THICKNESS','SURFACE_PREPARATION')))
  material='\n'.join(dict.fromkeys(e['context'] for e in found if e['label'] in ('MATERIAL_GRADE','CERTIFICATE')))
  return dict(painting=painting[:4000],material=material[:4000],entities=found,status='Review required' if found else 'Manual review required',notice='' if found else 'No specifications recognized. Scanned POs need OCR text or manual entry.',extractor='Local rules-based NER v1')
 except Exception:
  return dict(painting='',material='',entities=[],status='Manual review required',notice='Text extraction unavailable for this file. Enter the painting and material requirements manually.',extractor='Local rules-based NER v1')
