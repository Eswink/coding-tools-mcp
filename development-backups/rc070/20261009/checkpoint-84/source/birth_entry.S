/* Native-only birth continuation. No Python/libc/atfork/PLT calls. */
.text
.global rc_clone_exec_root
.type rc_clone_exec_root,@function
rc_clone_exec_root:
    push %rbx
    push %r12
    push %r13
    mov %rdi,%r12
    mov %rsi,%r13
    sub $96,%rsp
    mov %rsp,%rdi
    xor %eax,%eax
    mov $12,%ecx
    rep stosq
    movq $4096,0(%rsp)
    mov %r13,8(%rsp)
    movq $17,32(%rsp)
    mov $435,%eax
    mov %rsp,%rdi
    mov $88,%esi
    syscall
    test %rax,%rax
    jz .Lchild
    add $96,%rsp
    pop %r13
    pop %r12
    pop %rbx
    ret
.Lchild:
    mov 32(%r12),%rbx
    mov $157,%eax
    mov $36,%edi
    mov $1,%esi
    xor %edx,%edx
    xor %r10d,%r10d
    xor %r8d,%r8d
    syscall
    test %rax,%rax
    js .Lerror
    movl $0,88(%rsp)
    mov $157,%eax
    mov $37,%edi
    lea 88(%rsp),%rsi
    syscall
    test %rax,%rax
    js .Lerror
    cmpl $1,88(%rsp)
    jne .Lunsupported
    mov $112,%eax
    syscall
    test %rax,%rax
    js .Lerror
    mov 8(%r12),%rdi
    xor %esi,%esi
    mov $33,%eax
    syscall
    test %rax,%rax
    js .Lerror
    mov 16(%r12),%rdi
    mov $1,%esi
    mov $33,%eax
    syscall
    test %rax,%rax
    js .Lerror
    mov 24(%r12),%rdi
    mov $2,%esi
    mov $33,%eax
    syscall
    test %rax,%rax
    js .Lerror
    mov 0(%r12),%rdi
    cmp $3,%rdi
    je .Lexecready
    mov $3,%esi
    mov $524288,%edx
    mov $292,%eax
    syscall
    test %rax,%rax
    js .Lerror
.Lexecready:
    mov %rbx,%rdi
    cmp $4,%rdi
    je .Lerrready
    mov $4,%esi
    mov $524288,%edx
    mov $292,%eax
    syscall
    test %rax,%rax
    js .Lerror
.Lerrready:
    mov $4,%ebx
    mov $436,%eax
    mov $5,%edi
    mov $-1,%esi
    xor %edx,%edx
    syscall
    test %rax,%rax
    js .Lerror
    mov $322,%eax
    mov $3,%edi
    lea .Lempty(%rip),%rsi
    mov 40(%r12),%rdx
    mov 48(%r12),%r10
    mov $4096,%r8d
    syscall
    jmp .Lerror
.Lunsupported:
    mov $-95,%rax
.Lerror:
    neg %eax
    mov %eax,88(%rsp)
    mov $1,%eax
    mov %rbx,%rdi
    lea 88(%rsp),%rsi
    mov $4,%edx
    syscall
    mov $60,%eax
    mov $126,%edi
    syscall
    ud2
.size rc_clone_exec_root,.-rc_clone_exec_root
.section .rodata
.Lempty: .byte 0
.section .note.GNU-stack,"",@progbits
