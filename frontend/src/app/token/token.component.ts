import { Component, OnInit } from '@angular/core';
import { TokenService } from '../token.service';
import { Observable } from 'rxjs';
import { Token } from './token';

@Component({
  selector: 'app-token',
  templateUrl: './token.component.html',
  styleUrls: ['./token.component.css']
})

export class TokenComponent implements OnInit {
  public token : Observable<Token>;

  constructor(private tokenService: TokenService) { }

  ngOnInit() {
    this.token = this.tokenService.getToken();
  }

  selectToken(token : any){
    this.tokenService.saveToken(token);
  }

}
