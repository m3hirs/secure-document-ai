from __future__ import annotations
import random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select
from app.db.database import Base, SessionLocal, engine
from app.db.initialization import initialize_database
from app.db.models import Classification, Document, DocumentEvent, Tag, Team, User
random.seed(42); now=datetime.now(timezone.utc)
teams_data=[("Software","Product software"),("Machine Learning","ML systems"),("Design","Product design"),("Data Science","Analysis"),("Quality","Release quality"),("Marketing","Go-to-market")]
classes=[("Engineering","Technical content"),("Internal","Internal documentation"),("Confidential","Restricted information"),("Product","Product strategy"),("Research","Research material")]
tags="AI Architecture RAG API Security Compliance Analytics UX Release Database Cloud Testing Privacy Roadmap Mobile Platform Infrastructure Metrics Experiment Customer Integration Automation".split()
names=["Ava Patel","Noah Kim","Mia Chen","Liam Shah","Emma Wilson","Oliver Rao","Sophia Brown","Ethan Gupta","Isabella Lee","James Martin","Amelia Das","Lucas Roy","Harper Singh","Benjamin Ali","Evelyn Garcia","Henry Cooper","Grace Thomas","Alexander Park","Chloe Scott","Daniel Moore"]
def seed():
 initialize_database()
 with SessionLocal() as db:
  if db.scalar(select(func.count(User.id))): print("Database already seeded."); return
  teams=[Team(name=n,description=d) for n,d in teams_data]; classifications=[Classification(name=n,description=d) for n,d in classes]; tag_rows=[Tag(name=n) for n in tags]
  users=[User(name=n,email=n.lower().replace(" ",".")+"@example.com",created_at=now-timedelta(days=31+i)) for i,n in enumerate(names)]
  for i,user in enumerate(users): user.teams.extend((teams[i%6],teams[(i+1)%6]))
  db.add_all(teams+classifications+tag_rows+users); db.flush()
  for i in range(30):
   stamp=now-timedelta(days=random.randrange(30),hours=random.randrange(24)); doc=Document(filename=f"Enterprise_Document_{i+1:02}.pdf",file_path=f"data/documents/enterprise_document_{i+1:02}.pdf",file_type="application/pdf",file_size=random.randrange(80_000,8_000_000),page_count=random.randrange(2,60),classification=classifications[i%5],uploader=users[i%20],uploaded_at=stamp)
   doc.teams.extend([teams[i%6],teams[(i+1)%6]])
   if i%5==0: doc.teams.append(teams[(i+3)%6])
   doc.tags.extend(random.sample(tag_rows,3)); db.add(doc); db.flush()
   db.add_all([DocumentEvent(document=doc,user=doc.uploader,event_type="uploaded",timestamp=stamp,event_metadata={"source":"seed"}),DocumentEvent(document=doc,user=users[(i+2)%20],event_type="permissions_updated",timestamp=stamp+timedelta(minutes=10),event_metadata={"team_count":len(doc.teams)})])
  db.commit(); print("Seeded 20 users, 6 teams, 5 classifications, 21 tags, and 30 documents.")
if __name__=="__main__": seed()
