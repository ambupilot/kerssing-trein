"""A4 landscape EI administrative archive. Not an operational instruction."""
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth

COLORS = {"1":"#F6CDD2","2":"#D4E7E9","3":"#E4D5EC","4":"#F0E2C8",
"5":"#C9DEF3","6":"#EEE5AC","7":"#D8DDE8","8":"#F2CBC5",
"90":"#DCE9B9","95":"#EDCDD8"}
W,H=landscape(A4)
M,G=20,10
CW=(W-2*M-G)/2
R=M+CW+G
RED=HexColor("#CF252B")
GRAY=HexColor("#9BA6AF")
BLACK=HexColor("#26313B")

def build_ei_pdf(payload):
    selected={str(v) for v in payload.get("selected",[])}
    if not selected.issubset(COLORS):
        raise ValueError("Onbekende EI-selectie")
    details=payload.get("details") or {}
    checks=payload.get("checks") or {}
    stream=io.BytesIO()
    c=canvas.Canvas(stream,pagesize=(W,H))
    c.setTitle("European Instruction - administratief archief")
    def txt(x,y,s,size=7,bold=False):
        c.setFillColor(BLACK);c.setFont("Helvetica-Bold" if bold else "Helvetica",size)
        c.drawString(x,y,str(s))
    def rect(x,y,w,h,fill=None,red=False):
        c.setStrokeColor(RED if red else GRAY);c.setLineWidth(1.1 if red else .55)
        if fill:c.setFillColor(HexColor(fill))
        c.rect(x,y,w,h,fill=bool(fill),stroke=1)
    def tick(x,y,on=False,fixed=False):
        rect(x,y,8,8,"#FFFFFF")
        if on or fixed:
            c.setStrokeColor(RED if fixed else HexColor("#148D38"));c.setLineWidth(1.7)
            c.line(x+1,y+1,x+7,y+7);c.line(x+1,y+7,x+7,y+1)
    def value(x,top,w,h,label,val="",red=False,multi=False):
        rect(x,top-h,w,h,"#FFFFFF",red)
        txt(x+4,top-7,label,5.4)
        raw=str(val or "").replace("\\r","").strip()
        if not raw:return
        lines=[]
        font=9 if h>=20 else 7.5
        max_width=w-9
        for paragraph in raw.split("\\n") if multi else [raw.replace("\\n"," ")]:
            words=paragraph.split()
            line=""
            for word in words:
                test=(line+" "+word).strip()
                if stringWidth(test,"Helvetica",font)>max_width and line:
                    lines.append(line);line=word
                else:line=test
            if line:lines.append(line)
        available=h-13
        while font>=5.5:
            line_height=font+2
            if len(lines)*line_height<=available and all(stringWidth(line,"Helvetica",font)<=max_width for line in lines):
                break
            font-=.5
        if len(lines)*(font+2)>available or any(stringWidth(line,"Helvetica",font)>max_width for line in lines):
            raise ValueError("Tekst past niet in veld "+label)
        c.setFont("Helvetica",font)
        for i,line in enumerate(lines):c.drawString(x+4,top-10-font-i*(font+2),line)
    def section(x,top,n,title,h):
        rect(x,top-h,CW,h,COLORS[n])
        tick(x+9,top-23,n in selected)
        txt(x+24,top-20,("x."+n if n in ("90","95") else "EI "+n)+"  "+title,8,True)
        return top-34
    def check(x,y,n,code,label,fixed=False):
        tick(x,y-2, bool((checks.get(n) or {}).get(code)) and n in selected,fixed)
        txt(x+13,y,label,6.6)
    def d(n,key):
        return (details.get(n) or {}).get(key,"") if n in selected else ""
    top=H-20
    txt(M+4,top-9,"EUROPEAN INSTRUCTION",13,True)
    txt(R+4,top-9,"EUROPEAN INSTRUCTION",13,True)
    txt(M+4,top-23,"Machinist | zijde 1",7)
    txt(R+4,top-23,"Machinist | zijde 2",7)
    value(M+4,top-31,(CW-12)/2,20,"A  Treinnummer / Rangeernummer",payload.get("trainNumber",""),True)
    value(M+8+(CW-12)/2,top-31,(CW-12)/2,20,"D  Treindienstleidergebied",payload.get("dispatcherArea",""),True)
    y=top-61
    v=section(M,y,"1","Toestemming EOA / stoptonend sein te passeren",91)
    check(M+34,v,"1","1.10","Toestemming EOA / stoptonend sein / SMB")
    value(M+230,v+9,154,17,"1.11.1 km / 1.11.2 sein",d("1","location"),True)
    check(M+34,v-18,"1","1.20","Doorrijden in SH")
    check(M+34,v-37,"1","x.25","Hoeft niet op zicht te rijden")
    y-=96
    v=section(M,y,"2","Toestemming tot doorrijden na TRIP",66)
    check(M+34,v,"2","2.10","Doorrijden in SR als geen MA is ontvangen")
    check(M+34,v-18,"2","2.11","Doorrijden in SH")
    y-=71
    v=section(M,y,"3","Verplichting om stil te blijven staan",66)
    check(M+34,v,"3","3.10","Op huidige locatie")
    check(M+34,v-18,"3","3.20","Beschikbare MA verwijderen")
    y-=71
    v=section(M,y,"4","Intrekking van een instructie",53)
    check(M+34,v,"4","4.10","Operational Instruction met ID:")
    value(M+241,v+9,135,17,"4.11 ID",d("4","instruction_id"),True)
    y-=58
    for n,title in (("5","Verplichting om de snelheid te beperken"),("6","Verplichting om op zicht te rijden")):
        v=section(M,y,n,title,105)
        check(M+34,v,n,"x.41","Maximumsnelheid beperken tot")
        value(M+268,v+10,109,18,"x.42.1 km/h",d(n,"speed"),True)
        txt(M+100,v-28,"tussen / op*",6.7)
        value(M+182,v-15,96,18,"x.43 locatie",d(n,"between"),True)
        txt(M+283,v-28,"en",6.7)
        value(M+306,v-15,71,18,"x.44 locatie",d(n,"and"))
        txt(M+100,v-52,"van / bij*",6.7)
        value(M+182,v-39,96,18,"x.47 km/sein",d(n,"from"),True)
        txt(M+283,v-52,"tot",6.7)
        value(M+306,v-39,71,18,"x.48 km/sein",d(n,"to"))
        y-=110
    txt(M+5,y-7,"Aanvullende informatie (voetnoten)",6.7,True)
    txt(M+5,y-18,"* Doorhalen wat niet van toepassing is.",6.1)
    y=top-31
    v=section(R,y,"7","Toestemming om te vertrekken",110)
    check(R+34,v,"7","7.10","Toestemming te vertrekken in SR")
    check(R+34,v-18,"7","7.11","Toestemming te vertrekken in SH")
    check(R+34,v-36,"7","7.20","Toestemming EOA / SMB te passeren")
    value(R+273,v-26,100,17,"7.21 sein",d("7","signal"))
    check(R+34,v-54,"7","7.23","Verboden om override te gebruiken",True)
    y-=115
    v=section(R,y,"8","Toestemming defecte overweg te passeren",181)
    check(R+34,v,"8","8.40","Houd rekening met defecte overweg(en)")
    txt(R+34,v-19,"Tussen / op*",6.5)
    value(R+119,v-9,118,17,"x.43 locatie",d("8","between"),True)
    txt(R+244,v-19,"en",6.5)
    value(R+266,v-9,108,17,"x.44 locatie",d("8","and"))
    check(R+34,v-42,"8","8.50","Voor de overweg(en)")
    for i in range(9):
        rr,cc=divmod(i,3)
        value(R+34+cc*116,v-49-rr*24,108,19,"8."+str(51+i)+" km",d("8","km"+str(i+1)),i==0)
    check(R+34,v-125,"8","8.60","Bij naderen overweg(en): max. 10 km/h",True)
    check(R+34,v-142,"8","8.70","Bij naderen overweg(en): fluitsignalen",True)
    y-=186
    v=section(R,y,"90","Controleren infrastructuur",100)
    value(R+25,v+9,CW-50,44,"x.91 Reden van controle",d("90","reason"),True,True)
    txt(R+25,v-51,"Meld bevindingen aan:",6.5)
    value(R+25,v-44,CW-50,23,"x.92 Ontvanger",d("90","report"),True,True)
    y-=105
    v=section(R,y,"95","Aanvullende opdracht",75)
    value(R+25,v+10,CW-50,48,"x.96 Aanvullende opdracht",d("95","instruction"),True,True)
    y-=80
    value(R+4,y-1,(CW-12)/3,29,"Z  Identificatienummer",payload.get("identification",""),True)
    value(R+6+(CW-12)/3,y-1,(CW-12)/3,29,"B  Datum",payload.get("date",""),True)
    value(R+8+2*(CW-12)/3,y-1,(CW-12)/3,29,"Y  Tijd",payload.get("time",""),True)
    txt(R+5,y-46,"Administratieve kopie - niet gevalideerd voor operationeel gebruik.",6.1)
    c.save()
    return stream.getvalue()
