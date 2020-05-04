from .base36 import *
from ruqqus.__main__ import db
from ruqqus.classes import *

def get_user(username, graceful=False):

    x=db.query(User).filter(User.username.ilike(username)).first()
    if not x:
        if not graceful:
            abort(404)
        else:
            return None
    return x

def get_post(pid, v=None):

    i=base36decode(pid)

    if v:
        vt=db.query(Vote).filter_by(user_id=v.id, submission_id=i).subquery()


        items= db.query(Submission, vt.c.vote_type).filter(Submission.id==i).join(vt, isouter=True).first()
        
        x=items[0]
        x._voted=items[1] if items[1] else 0

    else:
        x=db.query(Submission).filter_by(id=base36decode(pid)).first()

    if not x:
        abort(404)
    return x

def get_comment(cid, v=None):

    i=base36decode(cid)

    if v:
        vt=db.query(CommentVote).filter_by(user_id=v.id, submission_id=i).subquery()


        items= db.query(Comment, vt.c.vote_type).filter(Comment.id==i).join(vt, isouter=True).first()
        
        x=items[0]
        x._voted=items[1] if items[1] else 0

    else:
        x=db.query(Comment).filter_by(id=base36decode(pid)).first()

    if not x:
        abort(404)
    return x

def get_board(bid):

    x=db.query(Board).filter_by(id=base36decode(bid)).first()
    if not x:
        abort(404)
    return x

def get_guild(name, graceful=False):

    name=name.lstrip('+')

    x=db.query(Board).filter(Board.name.ilike(name)).first()
    if not x:
        if not graceful:
            abort(404)
        else:
            return None
    return x

def get_domain(s):

    #parse domain into all possible subdomains
    parts=s.split(".")
    domain_list=set([])
    for i in range(len(parts)):
        new_domain=parts[i]
        for j in range(i+1, len(parts)):
            new_domain+="."+parts[j]

        domain_list.add(new_domain)

    domain_list=tuple(list(domain_list))

    doms=[x for x in db.query(Domain).filter(Domain.domain.in_(domain_list)).all()]

    if not doms:
        return None

    #return the most specific domain - the one with the longest domain property
    doms= sorted(doms, key=lambda x: len(x.domain), reverse=True)

    return doms[0]

def get_title(x):

    title=db.query(Title).filter_by(id=x).first()

    if not title:
        abort(400)

    else:
        return title


def get_mod(uid, bid):

    mod=db.query(ModRelationship).filter_by(board_id=bid,
                                            user_id=uid,
                                            accepted=True,
                                            invite_rescinded=False).first()

    return mod
