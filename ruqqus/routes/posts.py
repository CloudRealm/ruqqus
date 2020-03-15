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
from ruqqus.helpers.aws import *
from ruqqus.classes import *
from .front import frontlist

from PIL import Image

from flask import *
from ruqqus.__main__ import app, db, limiter, cache

BAN_REASONS=['',
             "URL shorteners are not permitted.",
             "Pornographic material is not permitted.",
             "Copyright infringement is not permitted."
            ]

ruqqus_logo=Image.open("/app/ruqqus/assets/images/logo/ruqqus_logo_square_white_fill.png").convert("RGBA")

@app.route("/post/<base36id>", methods=["GET"])
@auth_desired
def post_base36id(base36id, v=None):
    
    post=get_post(base36id)

    board=post.board

    if post.over_18 and not (v and v.over_18) and not session_over18(board):
        t=int(time.time())
        return render_template("errors/nsfw.html",
                               v=v,
                               t=t,
                               lo_formkey=make_logged_out_formkey(t),
                               board=post.board
                               )

    if board.is_banned and v.admin_level < 3:
        return render_template("board_banned.html",
                               v=v,
                               b=board)
        
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
        return render_template("submit.html",
                               v=v,
                               error="Please enter a better title.",
                               title=title, url=url,
                               body=request.form.get("body",""),
                               b=get_guild(request.form.get("board","")
                                           )
                               )
    elif len(title)>250:
        return render_template("submit.html",
                               v=v,
                               error="250 character limit for titles.",
                               title=title[0:250],
                               url=url,
                               body=request.form.get("body",""),
                               b=get_guild(request.form.get("board","")
                                           )
                               )

    parsed_url=urlparse(url)
    if not (parsed_url.scheme and parsed_url.netloc) and not request.form.get("body") and 'file' not in request.files:
        return render_template("submit.html",
                               v=v,
                               error="Please enter a URL or some text.",
                               title=title,
                               url=url,
                               body=request.form.get("body",""),
                               b=get_guild(request.form.get("board","")
                                           )
                               )

    #sanitize title
    title=sanitize(title, linkgen=False)

    #check for duplicate
    dup = db.query(Submission).filter_by(title=title,
                                         author_id=v.id,
                                         url=url,
                                         is_deleted=False
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
            try:
                embed=eval(domain_obj.embed_function)(url)
            except:
                embed=""
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

    if board.is_banned:
        return render_template("submit.html",
                               v=v,
                               error=f"+{board.name} has been demolished.",
                               title=title,
                               url=url
                               , body=request.form.get("body",""),
                               b=get_guild("general")
                               ), 403       
    
    if board.has_ban(v):
        return render_template("submit.html",
                               v=v,
                               error=f"You are exiled from +{board.name}.",
                               title=title,
                               url=url
                               , body=request.form.get("body",""),
                               b=get_guild("general")
                               ), 403

    if (board.restricted_posting or board.is_private) and not (board.can_submit(v)):
        return render_template("submit.html",
                               v=v,
                               error=f"You are not an approved contributor for +{board.name}.",
                               title=title,
                               url=url,
                               body=request.form.get("body",""),
                               b=get_guild(request.form.get("board","general"))
                               )

        
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
                                badge_id=6)
                db.add(new_alt)
                db.add(new_badge)
                db.commit()
            else:
                if identity not in v.alts:
                    abort(403)

            user_id=identity.id
            user_name=identity.username
        else:
            user_id=v.id
            user_name=v.username
    else:
        user_id=v.id
        user_name=v.username
                
                
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
    if len(body)>10000:

        return render_template("submit.html",
                               v=v,
                               error="10000 character limit for text body",
                               title=title,
                               text=body[0:10000],
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
                        post_public=not board.is_private,
                        author_name=user_name,
                        guild_name=board.name
                        )

    db.add(new_post)

    db.commit()

    vote=Vote(user_id=user_id,
              vote_type=1,
              submission_id=new_post.id
              )
    db.add(vote)
    db.commit()

    #check for uploaded image
    if request.files.get('file'):
        file=request.files['file']

        name=f'post/{new_post.base36id}/{secrets.token_urlsafe(16)}'


        #watermarky stuff
        file.save(name)
        image=Image.open(name)

        logo_resize = image.height/15

        logo_size=(int(ruqqus_logo.width/(ruqqus_logo.height/(image.height/15))),
                   int(image.height/15)
                   )

        ruqqus_logo_resized=ruqqus_logo.resize(logo_size,
                                               resample=Image.BICUBIC
                                               )
        position = (image.width-ruqqus_logo_resized.width,
                    image.height-ruqqus_logo_resized.height)


        image.paste(ruqqus_logo_resized,
                    position,
                    ruqqus_logo_resized)

        image.save(name)
        

        upload_file(name, open(name))
        
        #update post data
        new_post.url=f'https://i.ruqqus.com/{name}'
        new_post.is_image=True
        db.add(new_post)
        db.commit()

    
    #spin off thumbnail generation as  new thread
    elif new_post.url:
        new_thread=threading.Thread(target=thumbnail_thread,
                                    args=(new_post.base36id,)
                                    )
        new_thread.start()

    #expire the relevant caches: front page new, board new
    cache.delete_memoized(frontlist, sort="new")
    cache.delete_memoized(Board.idlist, board, sort="new")

    #print(f"Content Event: @{new_post.author.username} post {new_post.base36id}")

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

    #delete i.ruqqus.com
    if post.domain=="i.ruqqus.com":
        
        segments=post.url.split("/")
        pid=segments[2]
        rand=segments[3]
        if pid==post.base36id:
            key=f"post/{pid}/{rand}"
            delete_file(key)
        

    return "",204


@app.route("/embed/post/<pid>", methods=["GET"])
def embed_post_pid(pid):

    post=get_post(pid)

    if post.is_banned or post.board.is_banned:
        abort(410)

    return render_template("embeds/submission.html", p=post)
