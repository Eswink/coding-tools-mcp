/* Bare ELF entry: no CRT, constructors, loader or Python continuation. */
.text
.globl _start
.type _start,@function
_start:
    xorl %ebp, %ebp
    andq $-16, %rsp
    call rc_root_main
    movq %rax, %rdi
    movq $60, %rax
    syscall
    ud2
.size _start, .-_start
.section .note.GNU-stack,"",@progbits
