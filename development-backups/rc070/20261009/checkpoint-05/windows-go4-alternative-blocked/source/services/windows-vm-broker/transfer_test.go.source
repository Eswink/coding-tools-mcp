package main

import (
    "bytes"
    "context"
    "crypto/sha256"
    "strings"
    "testing"
)
func transferTestBinding() transferBinding {
    id := "11111111-1111-4111-8111-111111111111"
    return transferBinding{host:id, profile:"data-only", caller:"caller", source:strings.Repeat("1",40),
        session:id, operation:id, inputRelative:"input.txt", outputParent:"results", outputLeaf:"new.txt"}
}
func TestTransferAllBindingFieldsChangeDigest(t *testing.T) {
    original := transferTestBinding(); want, err := original.digest(); if err != nil { t.Fatal(err) }
    changes := []func(*transferBinding){
        func(b *transferBinding){b.host="22222222-2222-4222-8222-222222222222"},
        func(b *transferBinding){b.profile+="x"},func(b *transferBinding){b.caller+="x"},
        func(b *transferBinding){b.source=strings.Repeat("2",40)},
        func(b *transferBinding){b.session="22222222-2222-4222-8222-222222222222"},
        func(b *transferBinding){b.operation="22222222-2222-4222-8222-222222222222"},
        func(b *transferBinding){b.inputRelative="other.txt"},func(b *transferBinding){b.outputParent="other"},
        func(b *transferBinding){b.outputLeaf="other.txt"},
    }
    for _, change := range changes { b:=original;change(&b);got,e:=b.digest();if e!=nil || got==want {t.Fatal("field mismatch folded")}}
}
func TestTransferBoundEOFHashCancellationAndSingleConsumption(t *testing.T) {
    binding:=transferTestBinding(); h,_:=binding.digest(); data:=[]byte("data-only canary");digest:=sha256.Sum256(data)
    manifest:=workspaceStreamManifest{binding:h,direction:1,total:uint64(len(data)),digest:digest}
    wire,err:=workspaceEncode(manifest,data);if err!=nil {t.Fatal(err)}
    transfer,err:=receiveTransfer(context.Background(),binding,manifest.total,digest,bytes.NewReader(wire));if err!=nil {t.Fatal(err)}
    changed:=binding;changed.caller+="x";if _,e:=transfer.take(changed);e==nil {t.Fatal("foreign binding accepted")}
    got,err:=transfer.take(binding);if err!=nil || !bytes.Equal(got,data) {t.Fatal("exact data unavailable")}
    got[0]='X';if !bytes.Equal(transfer.data,data) {t.Fatal("detached owner shared mutable data")}
    if _,e:=transfer.take(binding);e==nil {t.Fatal("double consume accepted")}
    for _, broken := range [][]byte{wire[:len(wire)-1],append(bytes.Clone(wire),0)} {
        if _,e:=receiveTransfer(context.Background(),binding,manifest.total,digest,bytes.NewReader(broken));e==nil {t.Fatal("physical EOF invalid accepted")}
    }
    if _,e:=receiveTransfer(context.Background(),binding,workspaceMaximum+1,digest,bytes.NewReader(wire));e==nil {t.Fatal("size over cap")}
    ctx,cancel:=context.WithCancel(context.Background());cancel()
    if _,e:=receiveTransfer(ctx,binding,manifest.total,digest,bytes.NewReader(wire));e==nil {t.Fatal("cancelled receive accepted")}
}
func TestTransferRelativeAndMalformedIdentityReject(t *testing.T) {
    for _, path:=range []string{"", "../escape", "C:\\escape", "a:stream", "NUL .txt", "COM¹", "a//b", "a/\\b", "a."} {
        b:=transferTestBinding();b.inputRelative=path;if b.valid() {t.Fatal("unsafe relative name accepted",path)}
    }
    for _, path:=range []string{"src/配置\\a.rs","a b/c.d"} {if !transferRelative(path) {t.Fatal("bounded relative Unicode lost",path)}}
    b:=transferTestBinding();b.host="00000000-0000-0000-0000-000000000000";if b.valid() {t.Fatal("nil identity accepted")}
}
