use super::*;
use std::io::{self, Cursor};
use std::sync::{mpsc, Barrier};
use std::thread;
use std::time::Duration;

fn output_test_binding() -> RunBinding {
    let id = "11111111-1111-4111-8111-111111111111";
    RunBinding { host: id.into(), profile: "data-only".into(), caller: "caller".into(),
        source: "1".repeat(40), session: id.into(), operation: id.into(),
        input_relative: "input.txt".into(), output_parent: "results".into(), output_leaf: "new.txt".into() }
}
fn output_test_wire(binding: &RunBinding, data: &[u8], direction: u8) -> Vec<u8> {
    let binding_hash = output_binding_digest(binding).unwrap();
    let mut wire = Vec::new();
    let mut offset = 0usize; let mut sequence = 0u32;
    loop {
        let count = (data.len() - offset).min(OUTPUT_CHUNK);
        let mut header = [0u8; OUTPUT_HEADER];
        header[..8].copy_from_slice(b"CTMWIO02"); header[8] = direction;
        if offset == data.len() { header[9] = 1; }
        header[12..16].copy_from_slice(&sequence.to_le_bytes());
        header[16..24].copy_from_slice(&(offset as u64).to_le_bytes());
        header[24..32].copy_from_slice(&(data.len() as u64).to_le_bytes());
        header[32..36].copy_from_slice(&(count as u32).to_le_bytes());
        header[40..72].copy_from_slice(&binding_hash);
        wire.extend_from_slice(&header); wire.extend_from_slice(&data[offset..offset+count]);
        if offset == data.len() { break; }
        offset += count; sequence += 1;
    }
    wire
}
fn output_test_receive(binding: &RunBinding, data: &[u8]) -> OutputDataTransfer {
    receive_output_data(binding.clone(), data.len() as u64, Sha256::digest(data).into(),
        &mut Cursor::new(output_test_wire(binding,data,2)), OutputDataCancellation::default()).unwrap()
}

#[test]
fn output_direction_capacity_and_roundtrip() {
    let binding = output_test_binding();
    for size in [0,1,OUTPUT_CHUNK-1,OUTPUT_CHUNK,OUTPUT_CHUNK+1,OUTPUT_MAXIMUM] {
        let data = vec![7;size]; let owner = output_test_receive(&binding,&data);
        let mut got = owner.take_output_data(&binding).unwrap(); assert_eq!(got,data);
        if !got.is_empty() { got[0]^=1; assert_eq!(owner.0.lock().unwrap().data,data); }
        assert!(owner.take_output_data(&binding).is_err());
    }
    let data = b"direction canary"; let digest = Sha256::digest(data).into();
    assert!(receive_output_data(binding.clone(),data.len() as u64,digest,
        &mut Cursor::new(output_test_wire(&binding,data,1)),OutputDataCancellation::default()).is_err());
    assert!(receive_output_data(binding,OUTPUT_MAXIMUM as u64+1,digest,
        &mut Cursor::new(Vec::<u8>::new()),OutputDataCancellation::default()).is_err());
}

#[test]
fn output_binding_fields_and_terminal_foreign_attempt() {
    let original = output_test_binding(); let data=b"all nine fields";
    for i in 0..9 {
        let mut foreign = original.clone();
        match i {
            0=>foreign.host="22222222-2222-4222-8222-222222222222".into(),
            1=>foreign.profile.push('x'),2=>foreign.caller.push('x'),3=>foreign.source="2".repeat(40),
            4=>foreign.session="22222222-2222-4222-8222-222222222222".into(),
            5=>foreign.operation="22222222-2222-4222-8222-222222222222".into(),
            6=>foreign.input_relative="other.txt".into(),7=>foreign.output_parent="other".into(),
            _=>foreign.output_leaf="other.txt".into(),
        }
        assert!(foreign.valid()); assert_ne!(output_binding_digest(&foreign),output_binding_digest(&original));
        assert!(receive_output_data(foreign.clone(),data.len() as u64,Sha256::digest(data).into(),
            &mut Cursor::new(output_test_wire(&original,data,2)),OutputDataCancellation::default()).is_err());
        let owner = output_test_receive(&original,data); let copy=owner.clone();
        assert!(copy.take_output_data(&foreign).is_err()); assert!(owner.take_output_data(&original).is_err());
    }
    for bad in ["../escape","a:stream","NUL.txt"] {
        let mut binding=original.clone();binding.input_relative=bad.into();
        assert!(output_binding_digest(&binding).is_err());
    }
}

#[test]
fn output_header_sequence_offset_digest_and_EOF_reject() {
    let binding=output_test_binding();let data=b"bound output";let wire=output_test_wire(&binding,data,2);
    let mut rejected=vec![Vec::new(),wire[..7].to_vec(),wire[..wire.len()-72].to_vec(),wire[..wire.len()-1].to_vec()];
    let mut trailing=wire.clone();trailing.push(0);rejected.push(trailing);
    let mut replay=wire.clone();replay.extend_from_slice(&wire);rejected.push(replay);
    for index in [0,8,9,10,11,12,16,24,32,36,39,40,72] {
        let mut mutated=wire.clone();mutated[index]^=1;rejected.push(mutated);
    }
    let mut invalid_length=wire.clone();invalid_length[32..36].copy_from_slice(&32769u32.to_le_bytes());rejected.push(invalid_length);
    let mut premature=wire.clone();premature[9]=1;rejected.push(premature);
    let mut zero_data=wire.clone();zero_data[32..36].copy_from_slice(&0u32.to_le_bytes());rejected.push(zero_data);
    for bad in rejected {
        assert!(receive_output_data(binding.clone(),data.len() as u64,Sha256::digest(data).into(),
            &mut Cursor::new(bad),OutputDataCancellation::default()).is_err());
    }
    assert!(receive_output_data(binding,data.len() as u64,Sha256::digest(b"foreign").into(),
        &mut Cursor::new(wire),OutputDataCancellation::default()).is_err());
}

struct OutputReadFailure;
impl Read for OutputReadFailure {
    fn read(&mut self,_: &mut [u8]) -> io::Result<usize> { Err(io::Error::other("ordinary read failure")) }
}
struct OutputReadWithoutEOF { cursor: Cursor<Vec<u8>>, cancel: Option<OutputDataCancellation> }
impl Read for OutputReadWithoutEOF {
    fn read(&mut self,bytes: &mut [u8]) -> io::Result<usize> {
        let count=self.cursor.read(bytes)?;
        if count==0 {
            if let Some(stop)=&self.cancel { stop.cancel_output_data(); return Ok(0); }
            return Err(io::Error::other("ordinary missing EOF"));
        }
        Ok(count)
    }
}
struct OutputControlledBlock { cursor: Cursor<Vec<u8>>, entered: Option<mpsc::Sender<()>>, release: mpsc::Receiver<()> }
impl Read for OutputControlledBlock {
    fn read(&mut self,bytes: &mut [u8]) -> io::Result<usize> {
        if let Some(entered)=self.entered.take() {
            entered.send(()).map_err(io::Error::other)?;
            self.release.recv_timeout(Duration::from_secs(3)).map_err(io::Error::other)?;
        }
        self.cursor.read(bytes)
    }
}

#[test]
fn output_cancel_reader_error_and_blocked_reader_boundary() {
    let binding=output_test_binding();let data=b"cancel canary";let digest: [u8;32]=Sha256::digest(data).into();
    let stop=OutputDataCancellation::default();let copy=stop.clone();stop.cancel_output_data();
    assert!(copy.0.load(Ordering::Acquire));copy.cancel_output_data();assert!(stop.0.load(Ordering::Acquire));
    assert!(receive_output_data(binding.clone(),data.len() as u64,digest,&mut OutputReadFailure,stop).is_err());
    assert!(receive_output_data(binding.clone(),data.len() as u64,digest,&mut OutputReadFailure,OutputDataCancellation::default()).is_err());
    for cancel_eof in [false,true] {
        let stop=OutputDataCancellation::default();
        let mut reader=OutputReadWithoutEOF{cursor:Cursor::new(output_test_wire(&binding,data,2)),cancel:cancel_eof.then(||stop.clone())};
        assert!(receive_output_data(binding.clone(),data.len() as u64,digest,&mut reader,stop).is_err());
    }
    let stop=OutputDataCancellation::default();
    let owner=receive_output_data(binding.clone(),data.len() as u64,digest,
        &mut Cursor::new(output_test_wire(&binding,data,2)),stop.clone()).unwrap();
    stop.cancel_output_data();assert!(owner.take_output_data(&binding).is_err());assert!(owner.clone().take_output_data(&binding).is_err());
    let stop=OutputDataCancellation::default();let worker_stop=stop.clone();let worker_binding=binding.clone();
    let wire=output_test_wire(&binding,data,2);let (entered_tx,entered_rx)=mpsc::channel();
    let (release_tx,release_rx)=mpsc::channel();let (done_tx,done_rx)=mpsc::channel();
    let worker=thread::spawn(move||{
        let mut reader=OutputControlledBlock{cursor:Cursor::new(wire),entered:Some(entered_tx),release:release_rx};
        let result=receive_output_data(worker_binding,data.len() as u64,digest,&mut reader,worker_stop);
        done_tx.send(result.is_err()).unwrap();
    });
    entered_rx.recv_timeout(Duration::from_secs(3)).unwrap();stop.cancel_output_data();
    // DATA cancellation alone cannot unblock synchronous Read; release our own reader.
    assert!(matches!(done_rx.try_recv(),Err(mpsc::TryRecvError::Empty)));
    release_tx.send(()).unwrap();assert!(done_rx.recv_timeout(Duration::from_secs(3)).unwrap());worker.join().unwrap();
}

#[test]
fn output_clone_and_concurrent_once() {
    let binding=output_test_binding();let data=b"copy canary";let owner=output_test_receive(&binding,data);let clone=owner.clone();
    assert_eq!(clone.take_output_data(&binding).unwrap(),data);assert!(owner.take_output_data(&binding).is_err());
    let owner=output_test_receive(&binding,data);let start=Arc::new(Barrier::new(33));let mut workers=Vec::new();
    for _ in 0..32 {
        let owner=owner.clone();let binding=binding.clone();let start=start.clone();
        workers.push(thread::spawn(move||{start.wait();owner.take_output_data(&binding).is_ok()}));
    }
    start.wait();assert_eq!(workers.into_iter().map(|worker|worker.join().unwrap()).filter(|passed|*passed).count(),1);
    assert!(owner.take_output_data(&binding).is_err());
    let corrupt=output_test_receive(&binding,data);corrupt.0.lock().unwrap().data[0]^=1;
    assert!(corrupt.take_output_data(&binding).is_err());assert!(corrupt.take_output_data(&binding).is_err());
}

#[test]
fn output_mutex_poison_remains_denied() {
    let binding=output_test_binding();let owner=output_test_receive(&binding,b"poison canary");let clone=owner.clone();
    let worker=thread::spawn(move||{let _locked=clone.0.lock().unwrap();panic!("ordinary controlled state poison")});
    assert!(worker.join().is_err());assert!(owner.take_output_data(&binding).is_err());assert!(owner.clone().take_output_data(&binding).is_err());
}

#[test]
fn output_go_golden_vector_is_exact() {
    // Produced by actual Go1.24.13 unchanged original encoder/digest + frozen output consumer;
    // current 7vector receipt/output SHA8889d9f9… is private evidence, no borrowed old run.
    let binding=output_test_binding();assert_eq!(format!("{:x}",Sha256::digest(b"")),"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert_eq!(output_binding_digest(&binding).unwrap(),[
        0x88,0x13,0xb4,0xd6,0x37,0x84,0x11,0x00,0x33,0x78,0xfa,0xcb,0x2d,0xec,0x85,0x0d,
        0x69,0xed,0x7b,0xf2,0xb8,0x62,0x0e,0x21,0xdc,0xfc,0xfd,0xc3,0xf4,0x50,0xd0,0xfd]);
    for (size,want) in [(0,"d798a4eaf9079948d80f1299cfd37eebb37a93739954af09d5ae8a9dbe53e45c"),
        (1,"bfc5fff94a8898d6fe4a54ae62ed8b9bd2aa968d81737a0ed0583f0308fc91bd"),
        (32767,"90cda40d148339ce09491a2fbf1477910882b6e1034f67768da86599570ba3db"),
        (32768,"1b0210d4fc366e05856ec3cd78d0ab9e4ab12ff64791a98235d23947be5f4d96"),
        (32769,"d22adfceee3dc7242ef2dbe6bce1b70d4c0c3cb45dd008b5de420e6b9439b872"),
        (1048576,"f27d4f940bf301afe101cd37afa03c458e447ead1b83f4e8c8fb8e2545b5a0fe")] {
        assert_eq!(format!("{:x}",Sha256::digest(output_test_wire(&binding,&vec![7;size],2))),want);
    }
    let raw="43544d57494f3032020000000000000000000000000000000d000000000000000d000000000000008813b4d6378411003378facb2dec850d69ed7bf2b8620e21dcfcfdc3f450d0fde4bda0e5a5bd206f757470757443544d57494f303202010000010000000d000000000000000d0000000000000000000000000000008813b4d6378411003378facb2dec850d69ed7bf2b8620e21dcfcfdc3f450d0fd";
    let wire:Vec<u8>=raw.as_bytes().chunks_exact(2).map(|pair|u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap()).collect();
    let data="你好 output".as_bytes();assert_eq!(wire,output_test_wire(&binding,data,2));
    let owner=receive_output_data(binding.clone(),data.len() as u64,Sha256::digest(data).into(),&mut Cursor::new(wire),OutputDataCancellation::default()).unwrap();
    assert_eq!(owner.take_output_data(&binding).unwrap(),data);
}
