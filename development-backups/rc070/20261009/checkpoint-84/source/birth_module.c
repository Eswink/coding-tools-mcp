/* External ordinary prototype: actual creator escrow; no publisher authority. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdlib.h>
#include <errno.h>
#include "syscall_x86_64.h"
#include "root_image.inc"

enum { EMPTY=0, OWNED=1, CLOSED=2, UNKNOWN=3 };
enum { IMAGE=0, IN_READ=1, IN_WRITE=2, OUT_READ=3, OUT_WRITE=4,
       ERR_READ=5, ERR_WRITE=6, NULL_FD=7, PID_FD=8, NSLOTS=9 };
struct fd_slot { long fd; unsigned state; rc_u64 dev, ino; int error; };
struct rc_record {
    struct rc_record *next;
    struct fd_slot slots[NSLOTS];
    long pid;
    int created, terminal, reaped, code, status, unknown, launch_attempted;
    int boot, empty_seen, proto_eof, err_eof, proto_state, exec_error, wrappers;
};
struct rc_birth_plan {
    long exec_fd, in_fd, out_fd, null_fd, err_fd;
    const char *const *argv;
    const char *const *envp;
};
_Static_assert(__builtin_offsetof(struct rc_birth_plan,argv)==40,"asm argv ABI");
_Static_assert(__builtin_offsetof(struct rc_birth_plan,envp)==48,"asm env ABI");
extern long rc_clone_exec_root(const struct rc_birth_plan *,int *);
typedef struct { PyObject_HEAD struct rc_record *record; } RootObject;
static PyTypeObject RootType;
static struct rc_record *registry;
static unsigned registry_count;
#ifdef RC_ORDINARY_FAULTS
static int ordinary_fault;
#endif

static PyObject *native_error(long result) {
    errno=(int)-result;
    return PyErr_SetFromErrno(PyExc_OSError);
}
static int fd_identity(struct fd_slot *slot,int capture) {
    rc_u64 raw[18]={0};
    long got=rc_sc2(5,slot->fd,(long)raw);
    if (got<0) return (int)got;
    if (capture) { slot->dev=raw[0]; slot->ino=raw[1]; return 0; }
    return raw[0]==slot->dev && raw[1]==slot->ino ? 0 : -116;
}
static long own_fd(struct rc_record *r,int index,long fd) {
    if (fd<0) return fd;
    /* Actual handle enters preallocated ledger before fstat/assert/cancel. */
    r->slots[index].fd=fd; r->slots[index].state=OWNED;
    int result=fd_identity(&r->slots[index],1);
    return result<0 ? result : fd;
}
static void close_slot(struct rc_record *r,int index) {
    struct fd_slot *s=&r->slots[index];
    if (s->state!=OWNED) return;
    int observation=fd_identity(s,0);
    s->state=UNKNOWN; /* Remove retry permission before the actual close. */
    if (observation==-116) { s->error=116; r->unknown=1; return; }
    long result=rc_sc1(RC_NR_CLOSE,s->fd);
    if (result==0) s->state=CLOSED;
    else { s->error=(int)-result; r->unknown=1; }
    if (observation<0) { s->error=-observation; r->unknown=1; }
#ifdef RC_ORDINARY_FAULTS
    if (ordinary_fault==3 && result==0) {
        ordinary_fault=0; s->state=UNKNOWN; s->error=5; r->unknown=1;
    }
#endif
}
static void retire_record(struct rc_record *r) {
    /* Live records retain ALL transport and kernel ownership, even on error. */
    if (r->created && !r->terminal) { r->unknown=1; return; }
    for (int i=0;i<NSLOTS;i++) {
        /* Keep a genuine live/uncertain created pidfd in native escrow. */
        if (i==PID_FD && r->created && !r->reaped) continue;
        close_slot(r,i);
    }
}
static PyObject *deny_new(PyTypeObject *type,PyObject *args,PyObject *kw) {
    (void)type;(void)args;(void)kw;
    PyErr_SetString(PyExc_TypeError,"actual_creator_only_no_numeric_constructor");
    return NULL;
}
static PyObject *wrap_record(struct rc_record *r) {
    RootObject *o=PyObject_New(RootObject,&RootType);
    if (!o) return NULL;
    o->record=r;r->wrappers++;
    return (PyObject *)o;
}
static PyObject *native_create(PyObject *module,PyObject *ignored) {
    (void)module;(void)ignored;
#ifdef RC_ORDINARY_FAULTS
    if (ordinary_fault==1) { ordinary_fault=0; return native_error(-12); }
#endif
    if (registry_count>=64) return native_error(-28);
    struct rc_record *r=calloc(1,sizeof(*r));
    if (!r) return PyErr_NoMemory();
    for (int i=0;i<NSLOTS;i++) r->slots[i].fd=-1;
    /* The intrusive link exists before ANY actual kernel resource creation. */
    r->next=registry; registry=r; registry_count++;
    PyObject *object=wrap_record(r); /* Wrapper allocation also precedes birth. */
    if (!object) return NULL; /* Already-linked empty escrow remains reachable. */
    long result=own_fd(r,IMAGE,rc_sc2(RC_NR_MEMFD_CREATE,(long)"rc-native-root",0x13));
    if (result<0) goto fail;
    for (unsigned long offset=0;offset<RC_ROOT_IMAGE_LENGTH;) {
        result=rc_sc3(RC_NR_WRITE,r->slots[IMAGE].fd,
                     (long)(rc_root_image+offset),RC_ROOT_IMAGE_LENGTH-offset);
        if (result<=0) { if (!result) result=-5; goto fail; }
        offset+=(unsigned long)result;
    }
    result=rc_sc3(RC_NR_FCNTL,r->slots[IMAGE].fd,1033,0x0f);
    if (result<0) goto fail;
    result=rc_sc2(RC_NR_FCNTL,r->slots[IMAGE].fd,1034);
    if (result<0 || (result&0x0f)!=0x0f) { result=-95; goto fail; }
    /* Full actual-byte equality after seals, without caller-provided hashes. */
    for (unsigned long offset=0;offset<RC_ROOT_IMAGE_LENGTH;) {
        unsigned char block[4096];
        unsigned long n=RC_ROOT_IMAGE_LENGTH-offset;
        if (n>sizeof(block)) n=sizeof(block);
        result=rc_sc4(17,r->slots[IMAGE].fd,(long)block,n,offset);
        if (result!=(long)n) { if (result>=0) result=-5; goto fail; }
        for (unsigned long j=0;j<n;j++) if (block[j]!=rc_root_image[offset+j]) {
            result=-116; goto fail;
        }
        offset+=n;
    }
    for (int pair=0;pair<3;pair++) {
        int fds[2]={-1,-1};
        result=rc_sc2(RC_NR_PIPE2,(long)fds,RC_O_CLOEXEC|RC_O_NONBLOCK);
        if (result<0) goto fail;
        /* Both returned handles are ledgered before either metadata read. */
        int first=1+pair*2;
        r->slots[first].fd=fds[0];r->slots[first].state=OWNED;
        r->slots[first+1].fd=fds[1];r->slots[first+1].state=OWNED;
        result=fd_identity(&r->slots[first],1);
        if (result<0) goto fail;
        result=fd_identity(&r->slots[first+1],1);
        if (result<0) goto fail;
    }
    result=own_fd(r,NULL_FD,rc_sc4(RC_NR_OPENAT,RC_AT_FDCWD,(long)"/dev/null",2|RC_O_CLOEXEC,0));
    if (result<0) goto fail;
    for (int i=0;i<PID_FD;i++) if (r->slots[i].fd<3) { result=-95; goto fail; }
    const char *const argv[]={"rc-native-root",NULL};
    const char *const envp[]={"PATH=/usr/bin:/bin",NULL};
    struct rc_birth_plan plan={r->slots[IMAGE].fd,r->slots[IN_READ].fd,
        r->slots[OUT_WRITE].fd,r->slots[NULL_FD].fd,r->slots[ERR_WRITE].fd,argv,envp};
#ifdef RC_ORDINARY_FAULTS
    if (ordinary_fault==4) { ordinary_fault=0; plan.exec_fd=-1; }
#endif
    rc_u64 blocked=~0UL,oldmask=0;
    result=rc_sc4(RC_NR_RT_SIGPROCMASK,0,(long)&blocked,(long)&oldmask,8);
    if (result<0) goto fail;
    int actual_pidfd=-1;
    result=rc_clone_exec_root(&plan,&actual_pidfd);
    long creation=result;
    if (creation>0) {
        r->created=1;r->pid=creation;
        /* Fixed stores into already-linked native storage, before Py/unblock. */
        r->slots[PID_FD].fd=actual_pidfd;r->slots[PID_FD].state=OWNED;
        if (actual_pidfd<0 || fd_identity(&r->slots[PID_FD],1)<0) r->unknown=1;
    }
    long restored=rc_sc4(RC_NR_RT_SIGPROCMASK,RC_SIG_SETMASK,(long)&oldmask,0,8);
    if (restored<0) { r->unknown=1; result=restored; goto fail; }
    if (creation<0) { result=creation; goto fail; }
    close_slot(r,IMAGE);close_slot(r,IN_READ);close_slot(r,OUT_WRITE);
    close_slot(r,ERR_WRITE);close_slot(r,NULL_FD);
#ifdef RC_ORDINARY_FAULTS
    if (ordinary_fault==2) { ordinary_fault=0; result=-5; goto fail; }
#endif
    return object;
fail:
    /* No primary Python error exists yet: preserve this actual native errno. */
    retire_record(r);
    Py_DECREF(object); /* Destructor cannot unlink actual uncertain escrow. */
    return native_error(result<0?result:-5);
}
static PyObject *native_retained(PyObject *module,PyObject *ignored) {
    (void)module;(void)ignored;
    PyObject *list=PyList_New(0);
    if (!list) return NULL;
    for (struct rc_record *r=registry;r;r=r->next) {
        PyObject *o=wrap_record(r);
        if (!o || PyList_Append(list,o)<0) { Py_XDECREF(o);Py_DECREF(list);return NULL; }
        Py_DECREF(o);
    }
    return list;
}
static PyObject *owner_send(PyObject *obj,PyObject *arg) {
    struct rc_record *r=((RootObject *)obj)->record;
    if (!PyBytes_CheckExact(arg) || PyBytes_GET_SIZE(arg)<=0 || PyBytes_GET_SIZE(arg)>512) {
        PyErr_SetString(PyExc_ValueError,"fixed_bounded_protocol_bytes");return NULL;
    }
    if (r->slots[IN_WRITE].state!=OWNED) return native_error(-9);
    int identity=fd_identity(&r->slots[IN_WRITE],0);
    if (identity<0) {r->unknown=1;return native_error(identity);}
    const char *raw=PyBytes_AS_STRING(arg);
    if (raw[0]=='L') r->launch_attempted=1; /* Sticky before first syscall. */
    long got=rc_sc3(RC_NR_WRITE,r->slots[IN_WRITE].fd,(long)raw,PyBytes_GET_SIZE(arg));
    if (got<0) return native_error(got);
    return PyLong_FromLong(got);
}
static void consume_protocol(struct rc_record *r,const char *raw,long n) {
    for (long i=0;i<n;i++) {
        char expected=r->proto_state==0?'B':r->proto_state==1?'\n':r->proto_state==2?'E':'\n';
        if (r->proto_state>=4 || raw[i]!=expected) {r->unknown=1;continue;}
        r->proto_state++;
        if (r->proto_state==2) r->boot=1;
        if (r->proto_state==4) r->empty_seen=1;
    }
}
static PyObject *owner_read(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    if (r->slots[OUT_READ].state!=OWNED) return native_error(-9);
    int identity=fd_identity(&r->slots[OUT_READ],0);
    if (identity<0) {r->unknown=1;return native_error(identity);}
    char raw[512];long n=rc_sc3(RC_NR_READ,r->slots[OUT_READ].fd,(long)raw,sizeof(raw));
    if (n==-RC_EAGAIN || n==-RC_EINTR) Py_RETURN_NONE;
    if (n<0) {r->unknown=1;return native_error(n);}
    if (!n) r->proto_eof=1;
    else consume_protocol(r,raw,n);
    return PyBytes_FromStringAndSize(raw,n);
}
static PyObject *owner_exec_error(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    if (r->slots[ERR_READ].state!=OWNED) return native_error(-9);
    int identity=fd_identity(&r->slots[ERR_READ],0);
    if (identity<0) {r->unknown=1;return native_error(identity);}
    unsigned char raw[32];long n=rc_sc3(RC_NR_READ,r->slots[ERR_READ].fd,(long)raw,sizeof(raw));
    if (n==-RC_EAGAIN || n==-RC_EINTR) Py_RETURN_NONE;
    if (n<0) {r->unknown=1;return native_error(n);}
    if (!n) r->err_eof=1;
    else r->exec_error=1; /* CLOEXEC EOF alone never asserts successful exec. */
    return PyBytes_FromStringAndSize((const char *)raw,n);
}
static PyObject *owner_observe(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    if (!r->created || r->slots[PID_FD].state!=OWNED || r->reaped) return native_error(-9);
    int identity=fd_identity(&r->slots[PID_FD],0);
    if (identity<0) {r->unknown=1;return native_error(identity);}
    struct rc_siginfo info={0};
    long got=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,r->slots[PID_FD].fd,(long)&info,
                   RC_WEXITED|RC_WNOHANG|RC_WNOWAIT,0);
    if (got<0) {r->unknown=1;return native_error(got);}
    if (!info.pid) Py_RETURN_NONE;
    if (info.pid!=r->pid || info.code<1 || info.code>3) {r->unknown=1;return native_error(-116);}
    r->terminal=1;r->code=info.code;r->status=info.status;
    return Py_BuildValue("(ii)",info.code,info.status);
}
static PyObject *owner_abort_before_launch(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    /* Only native internal first-byte state permits sole-root abort. */
    if (!r->created || r->launch_attempted || r->reaped ||
        r->slots[PID_FD].state!=OWNED) return native_error(-1);
    int identity=fd_identity(&r->slots[PID_FD],0);
    if (identity<0) {r->unknown=1;return native_error(identity);}
    struct rc_siginfo info={0};
    long got=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,r->slots[PID_FD].fd,(long)&info,
                   RC_WEXITED|RC_WNOHANG|RC_WNOWAIT,0);
    if (got<0) {r->unknown=1;return native_error(got);}
    if (info.pid) {
        if (info.pid!=r->pid || info.code<1 || info.code>3) {
            r->unknown=1;return native_error(-116);
        }
        r->terminal=1;r->code=info.code;r->status=info.status;
        Py_RETURN_NONE;
    }
    got=rc_sc4(RC_NR_PIDFD_SEND_SIGNAL,r->slots[PID_FD].fd,9,0,0);
    if (got<0) {r->unknown=1;return native_error(got);}
    /* Actual SIGKILL is cleanup only; not an ACK, EMPTY or command result. */
    Py_RETURN_NONE;
}
static PyObject *owner_reap(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    if (!r->terminal || r->reaped || r->slots[PID_FD].state!=OWNED) return native_error(-9);
    struct rc_siginfo info={0};
    long got=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,r->slots[PID_FD].fd,(long)&info,RC_WEXITED|RC_WNOHANG,0);
    if (got<0) {r->unknown=1;return native_error(got);}
    if (info.pid!=r->pid || info.code!=r->code || info.status!=r->status) {
        r->unknown=1;return native_error(-116);
    }
    r->reaped=1;Py_RETURN_NONE;
}
static int root_closed_truth(struct rc_record *r) {
    if (!r->created || !r->terminal || !r->reaped || !r->proto_eof || !r->err_eof || r->unknown) return 0;
    if (r->launch_attempted && !r->empty_seen) return 0;
    for (int i=0;i<NSLOTS;i++) if (r->slots[i].state!=CLOSED) return 0;
    return 1; /* Local native lifecycle only; never command/publisher authority. */
}
static PyObject *owner_snapshot(PyObject *obj,PyObject *ignored) {
    (void)ignored;struct rc_record *r=((RootObject *)obj)->record;
    PyObject *errors=PyList_New(0);
    if (!errors) return NULL;
    for (int i=0;i<NSLOTS;i++) if (r->slots[i].error) {
        PyObject *e=Py_BuildValue("(ii)",i,r->slots[i].error);
        if (!e || PyList_Append(errors,e)<0) {Py_XDECREF(e);Py_DECREF(errors);return NULL;}
        Py_DECREF(e);
    }
    PyObject *out=Py_BuildValue("{s:i,s:i,s:i,s:i,s:i,s:i,s:i,s:i,s:i,s:i,s:O}",
        "created",r->created,"boot",r->boot,"empty",r->empty_seen,
        "launch_attempted",r->launch_attempted,"terminal",r->terminal,"reaped",r->reaped,
        "proto_eof",r->proto_eof,"exec_eof",r->err_eof,"unknown",r->unknown,
        "native_closed",root_closed_truth(r),"close_errors",errors);
    Py_DECREF(errors);return out;
}
static PyObject *owner_retire(PyObject *obj,PyObject *ignored) {
    (void)ignored;retire_record(((RootObject *)obj)->record);
    return owner_snapshot(obj,NULL);
}
static void owner_dealloc(PyObject *obj) {
    struct rc_record *r=((RootObject *)obj)->record;
    if (--r->wrappers==0) retire_record(r);
    /* Registry always retains original actual record, especially UNKNOWN. */
    PyObject_Del(obj);
}
#ifdef RC_ORDINARY_FAULTS
static PyObject *native_arm_fault(PyObject *module,PyObject *arg) {
    (void)module;long value=PyLong_AsLong(arg);
    if (PyErr_Occurred()) return NULL;
    if (value<0 || value>4) {PyErr_SetString(PyExc_ValueError,"ordinary_fault_range");return NULL;}
    ordinary_fault=(int)value;Py_RETURN_NONE;
}
#endif
static PyMethodDef owner_methods[]={
    {"send",owner_send,METH_O,NULL},{"read",owner_read,METH_NOARGS,NULL},
    {"exec_error",owner_exec_error,METH_NOARGS,NULL},{"observe",owner_observe,METH_NOARGS,NULL},
    {"abort_before_launch",owner_abort_before_launch,METH_NOARGS,NULL},
    {"reap",owner_reap,METH_NOARGS,NULL},{"retire",owner_retire,METH_NOARGS,NULL},
    {"snapshot",owner_snapshot,METH_NOARGS,NULL},{NULL,NULL,0,NULL}
};
static PyTypeObject RootType={PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="_rc_native_birth.CreatedRoot",.tp_basicsize=sizeof(RootObject),
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_new=deny_new,.tp_dealloc=owner_dealloc,
    .tp_methods=owner_methods
};
static PyMethodDef module_methods[]={
    {"create",native_create,METH_NOARGS,NULL},{"retained",native_retained,METH_NOARGS,NULL},
#ifdef RC_ORDINARY_FAULTS
    {"arm_ordinary_fault",native_arm_fault,METH_O,NULL},
#endif
    {NULL,NULL,0,NULL}
};
static struct PyModuleDef module={PyModuleDef_HEAD_INIT,"_rc_native_birth",NULL,-1,module_methods,
    NULL,NULL,NULL,NULL};
PyMODINIT_FUNC PyInit__rc_native_birth(void) {
    /* Source Stage I import is forbidden; even eventual PyInit has no native effects. */
    if (PyType_Ready(&RootType)<0) return NULL;
    PyObject *m=PyModule_Create(&module);
    if (!m) return NULL;
    Py_INCREF(&RootType);
    if (PyModule_AddObject(m,"CreatedRoot",(PyObject *)&RootType)<0) {
        Py_DECREF(&RootType);Py_DECREF(m);return NULL;
    }
    return m;
}
