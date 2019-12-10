from urllib.parse import urlparse, ParseResult, urlunparse
import mistletoe
from sqlalchemy import func
from bs4 import BeautifulSoup
import secrets

from ruqqus.helpers.wrappers import *
from ruqqus.helpers.base36 import *
from ruqqus.helpers.sanitize import *
from ruqqus.helpers.filters import *
from ruqqus.helpers.embed import *
from ruqqus.helpers.markdown import *
from ruqqus.classes import *
from flask import *
from ruqqus.__main__ import app, db, limiter

BAN_REASONS=['',
             "URL shorteners are not permitted.",
             "Pornographic material is not permitted.",
             "Copyright infringement is not permitted."
            ]






@app.route("/post/<base36id>", methods=["GET"])
@auth_desired
def post_base36id(base36id, v=None):
    
    base10id = base36decode(base36id)
    
    post=db.query(Submission).filter_by(id=base10id).first()
    if not post:
        abort(404)
        
    return post.rendered_page(v=v)

@app.route("/submit", methods=["GET"])
@is_not_banned
def submit_get(v):
    return render_template("submit.html",
                           v=v,
                           board=request.args.get("guild","")
                           )




@app.route("/submit", methods=['POST'])
@limiter.limit("6/minute")
@is_not_banned
@validate_formkey
def submit_post(v):

    title=request.form.get("title","")

    url=request.form.get("url","")

    if len(title)<10:
        return render_template("submit.html", v=v, error="Please enter a better title.", title=title, url=url, body=request.form.get("body",""), board=request.form.get("board",""))

    parsed_url=urlparse(url)
    if not (parsed_url.scheme and parsed_url.netloc) and not request.form.get("body"):
        return render_template("submit.html", v=v, error="Please enter a URL or some text.", title=title, url=url, body=request.form.get("body",""), board=request.form.get("board",""))

    #sanitize title
    title=sanitize(title, linkgen=False)

    #check for duplicate
    dup = db.query(Submission).filter_by(title=title,
                                         author_id=v.id,
                                         url=url
                                         ).first()

    if dup:
        return redirect(dup.permalink)

    
    #check for domain specific rules

    parsed_url=urlparse(url)

    domain=parsed_url.netloc

    ##all possible subdomains
    parts=domain.split(".")
    domains=[]
    for i in range(len(parts)):
        new_domain=parts[i]
        for j in range(i+1, len(parts)):
            new_domain+="."+parts[j]

        domains.append(new_domain)
        
    domain_obj=db.query(Domain).filter(Domain.domain.in_(domains)).first()

    if domain_obj:
        if not domain_obj.can_submit:
            return render_template("submit.html",v=v, error=BAN_REASONS[domain_obj.reason], title=title, url=url, body=request.form.get("body",""), board=request.form.get("board",""))

    #board
    board_name=request.form.get("board","general")
    board_name=board_name.lstrip("+")
    
    board=db.query(Board).filter(Board.name.ilike(board_name)).first()
    if not board:
        board=db.query(Board).filter_by(id=1).first()
    
    if board.has_ban(v):
        return render_template("submit.html",v=v, error=f"You are exiled from +{board.name}.", title=title, url=url, body=request.form.get("body",""), board=request.form.get("board",""))

            
    #Huffman-Ohanian growth method
    if v.admin_level >=2:

        name=request.form.get("username",None)
        if name:

            identity=db.query(User).filter(User.username.ilike(name)).first()
            if not identity:
                if not re.match("^\w{5,25}$", name):
                    abort(422)
                    
                identity=User(username=name,
                              password=secrets.token_hex(16),
                              email=None,
                              created_utc=int(time.time()),
                              creation_ip=request.remote_addr)
                identity.passhash=v.passhash
                db.add(identity)
                db.commit()

                new_alt=Alt(user1=v.id,
                            user2=identity.id)

                new_badge=Badge(user_id=identity.id,
                                badge_id=1)
                db.add(new_alt)
                db.add(new_badge)
                db.commit()
            else:
                if identity not in v.alts:
                    abort(403)

            user_id=identity.id
        else:
            user_id=v.id
    else:
        user_id=v.id
                
                
    #Force https for submitted urls
    if request.form.get("url"):
        new_url=ParseResult(scheme="https",
                            netloc=parsed_url.netloc,
                            path=parsed_url.path,
                            params=parsed_url.params,
                            query=parsed_url.query,
                            fragment=parsed_url.fragment)
        url=urlunparse(new_url)
    else:
        url=""

    #now make new post

    body=request.form.get("body","")

    with CustomRenderer() as renderer:
        body_md=renderer.render(mistletoe.Document(body))
    body_html = sanitize(body_md, linkgen=True)

    #check for embeddable video
    domain=parsed_url.netloc
    embed=""
    if domain.endswith(("youtube.com","youtu.be")):
        embed=youtube_embed(url)

    
    
    new_post=Submission(title=title,
                        url=url,
                        author_id=user_id,
                        body=body,
                        body_html=body_html,
                        embed_url=embed,
                        domain_ref=domain_obj.id if domain_obj else None,
                        board_id=board.id,
                        original_board_id=board.id
                        )

    db.add(new_post)

    db.commit()

    vote=Vote(user_id=user_id,
              vote_type=1,
              submission_id=new_post.id
              )
    db.add(vote)
    db.commit()

    return redirect(new_post.permalink)
    
@app.route("/api/nsfw/<pid>/<x>", methods=["POST"])
@auth_required
@validate_formkey
def api_nsfw_pid(pid, x, v):

    try:
        x=bool(int(x))
    except:
        abort(400)

    post=get_post(pid)

    if not v.admin_level >=3 and not post.author_id==v.id and not post.board.has_mod(v):
        abort(403)
        
    post.over_18=x
    db.add(post)
    db.commit()

    return "", 204
