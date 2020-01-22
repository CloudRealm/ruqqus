from urllib.parse import urlparse, ParseResult, urlunparse, urlencode
import mistletoe
from sqlalchemy import func
from bs4 import BeautifulSoup
import secrets
import threading

from ruqqus.helpers.wrappers import *
from ruqqus.helpers.base36 import *
from ruqqus.helpers.sanitize import *
from ruqqus.helpers.filters import *
from ruqqus.helpers.embed import *
from ruqqus.helpers.markdown import *
from ruqqus.helpers.get import *
from ruqqus.helpers.thumbs import *
from ruqqus.helpers.session import *
from ruqqus.classes import *
from .front import frontlist
from flask import *
from ruqqus.__main__ import app, db, limiter, cache

BAN_REASONS=['',
             "URL shorteners are not permitted.",
             "Pornographic material is not permitted.",
             "Copyright infringement is not permitted."
            ]






@app.route("/post/<base36id>", methods=["GET"])
@auth_desired
def post_base36id(base36id, v=None):
    
    post=get_post(base36id)

    if post.over_18 and not (v and v.over_18) and not session_over18(post.board):
        t=int(time.time())
        return render_template("errors/nsfw.html",
                               v=v,
                               t=t,
                               lo_formkey=make_logged_out_formkey(t),
                               board=post.board
                               )
        
    return post.rendered_page(v=v)

@app.route("/submit", methods=["GET"])
@is_not_banned
def submit_get(v):

    board=request.args.get("guild","general")
    b=get_guild(board, graceful=True)
    if not b:
        b=get_guild("general")
    
    return render_template("submit.html",
                           v=v,
                           b=b
                           )


@app.route("/edit_post/<pid>", methods=["POST"])
@is_not_banned
@validate_formkey
def edit_post(pid, v):
    
    p = get_post(pid)

    if not p.author_id == v.id:
        abort(403)

    if p.is_banned:
        abort(403)

    if p.board.has_ban(v):
        abort(403)

    body = request.form.get("body", "")
    with CustomRenderer() as renderer:
        body_md = renderer.render(mistletoe.Document(body))
    body_html = sanitize(body_md, linkgen=True)

    p.body = body
    p.body_html = body_html
    p.edited_utc = int(time.time())

    db.add(p)
    db.commit()

    return redirect(p.permalink)

@app.route("/submit", methods=['POST'])
@limiter.limit("6/minute")
@is_not_banned
@tos_agreed
@validate_formkey
def submit_post(v):

    title=request.form.get("title","")

    url=request.form.get("url","")

    if len(title)<10:
        return render_template("submit.html", v=v, error="Please enter a better title.", title=title, url=url, body=request.form.get("body",""), b=get_guild(request.form.get("board","")))

    parsed_url=urlparse(url)
    if not (parsed_url.scheme and parsed_url.netloc) and not request.form.get("body"):
        return render_template("submit.html", v=v, error="Please enter a URL or some text.", title=title, url=url, body=request.form.get("body",""), b=get_guild(request.form.get("board","")))

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

    # check ban status
    domain_obj=get_domain(domain)
    if domain_obj:
        if not domain_obj.can_submit:
            return render_template("submit.html",
                                   v=v,
                                   error=BAN_REASONS[domain_obj.reason],
                                   title=title,
                                   url=url,
                                   body=request.form.get("body",""),
                                   b=get_guild(request.form.get("board","general"))
                                   )

        #check for embeds
        if domain_obj.embed_function:

            embed=eval(domain_obj.embed_function)(url)
        else:
            embed=""
    else:
        embed=""
        

    #board
    board_name=request.form.get("board","general")
    board_name=board_name.lstrip("+")
    
    board=get_guild(board_name, graceful=True)
    if not board:
        board=get_guild('general')
    
    if board.has_ban(v):
        return render_template("submit.html",v=v, error=f"You are exiled from +{board.name}.", title=title, url=url, body=request.form.get("body",""), b=get_guild("general")), 403

    if (board.restricted_posting or board.is_private) and not (board.can_submit(v)):
        return render_template("submit.html",v=v, error=f"You are not an approved contributor for +{board.name}.", title=title, url=url, body=request.form.get("body",""), b=get_guild(request.form.get("board","general")))

        
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

    #catch too-long body
    if len(body)>6000:

        return render_template("submit.html",
                               v=v,
                               error="2000 character limit for text body",
                               title=title,
                               text=body[0:6000],
                               url=url,
                               b=get_guild(request.form.get("board","general"))
                               ), 400

    if len(url)>2048:

        return render_template("submit.html",
                               v=v,
                               error="URLs cannot be over 2048 characters",
                               title=title,
                               text=body[0:2000],
                               b=get_guild(request.form.get("board","general"))
                               ), 400

    with CustomRenderer() as renderer:
        body_md=renderer.render(mistletoe.Document(body))
    body_html = sanitize(body_md, linkgen=True)

    #check for embeddable video
    domain=parsed_url.netloc

    
    
    new_post=Submission(title=title,
                        url=url,
                        author_id=user_id,
                        body=body,
                        body_html=body_html,
                        embed_url=embed,
                        domain_ref=domain_obj.id if domain_obj else None,
                        board_id=board.id,
                        original_board_id=board.id,
                        over_18=(bool(request.form.get("over_18","")) or board.over_18),
                        post_public=not board.is_private
                        )

    db.add(new_post)

    db.commit()

    vote=Vote(user_id=user_id,
              vote_type=1,
              submission_id=new_post.id
              )
    db.add(vote)
    db.commit()

    
    #spin off thumbnail generation as  new thread
    if new_post.url and not embed:
        new_thread=threading.Thread(target=thumbnail_thread,
                                    args=(new_post.base36id,)
                                    )
        new_thread.start()

    #expire the relevant caches: front page new, board new
    cache.delete_memoized(frontlist, sort="new")
    cache.delete_memoized(Board.idlist, board, sort="new")

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

@app.route("/delete_post/<pid>", methods=["POST"])
@auth_required
@validate_formkey
def delete_post_pid(pid, v):

    post=get_post(pid)
    if not post.author_id==v.id:
        abort(403)

    post.is_deleted=True
    db.add(post)
    db.commit()

    return "",204


@app.route("/embed/post/<pid>", methods=["GET"])
def embed_post_pid(pid):

    post=get_post(pid)

    return render_template("embeds/submission.html", p=post)
